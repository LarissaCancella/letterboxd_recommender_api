import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import time
import math
import datetime
from itertools import chain
import asyncio
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError
from tqdm import tqdm
from pprint import pprint

from db.db_connect import connect_to_db
from utils import helpers

async def fetch(url, session, input_data={}):
    async with session.get(url) as response:
        try:
            return await response.read(), input_data
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None, None

async def get_page_counts(usernames, users_cursor):
    url = "https://letterboxd.com/{}/films/"
    tasks = []

    async with ClientSession() as session:
        for username in usernames:
            task = asyncio.ensure_future(
                fetch(url.format(username), session, {"username": username})
            )
            tasks.append(task)

        responses = await asyncio.gather(*tasks)
        responses = [x for x in responses if x]

        update_operations = []
        for response in responses:
            soup = BeautifulSoup(response[0], "lxml")
            try:
                page_link = soup.findAll("li", class_="paginate-page")[-1]
                num_pages = int(page_link.find("a").text.replace(",", ""))
            except IndexError:
                num_pages = 1

            user = users_cursor.find_one({"username": response[1]["username"]})
            previous_num_pages = user.get("num_ratings_pages", 0)

            new_pages = min(num_pages, max(num_pages - previous_num_pages + 1, 10)) if num_pages < 128 else 10

            update_operations.append(
                UpdateOne(
                    {"username": response[1]["username"]},
                    {
                        "$set": {
                            "num_ratings_pages": num_pages,
                            "recent_page_count": new_pages,
                            "last_updated": datetime.datetime.now(),
                        }
                    },
                    upsert=True,
                )
            )

        if update_operations:
            try:
                users_cursor.bulk_write(update_operations, ordered=False)
            except BulkWriteError as bwe:
                pprint(bwe.details)

async def generate_ratings_operations(response, send_to_db=True, return_unrated=False):
    soup = BeautifulSoup(response[0], "lxml")
    reviews = soup.findAll("li", class_="poster-container")

    ratings_operations = []
    movie_operations = []

    for review in reviews:
        movie_id = review.find("div", class_="film-poster")["data-target-link"].split("/")[-2]
        rating = review.find("span", class_="rating")
        
        if rating:
            rating_val = int(rating["class"][-1].split("-")[-1])
        elif return_unrated:
            rating_val = -1
        else:
            continue

        rating_object = {
            "movie_id": movie_id,
            "rating_val": rating_val,
            "user_id": response[1]["username"],
        }

        skeleton_movie_object = {"movie_id": movie_id}

        if not send_to_db:
            ratings_operations.append(rating_object)
        else:
            ratings_operations.append(
                UpdateOne(
                    {"user_id": response[1]["username"], "movie_id": movie_id},
                    {"$set": rating_object},
                    upsert=True,
                )
            )
            movie_operations.append(
                UpdateOne(
                    {"movie_id": movie_id}, {"$set": skeleton_movie_object}, upsert=True
                )
            )

    return ratings_operations, movie_operations

async def get_user_ratings(username, db_cursor=None, mongo_db=None, store_in_db=True, num_pages=None, return_unrated=False):
    url = "https://letterboxd.com/{}/films/by/date/page/{}/"

    if not num_pages:
        user = db_cursor.find_one({"username": username})
        num_pages = user["recent_page_count"]

    async with ClientSession() as session:
        tasks = [asyncio.ensure_future(fetch(url.format(username, i + 1), session, {"username": username})) for i in range(num_pages)]
        scrape_responses = await asyncio.gather(*tasks)
        scrape_responses = [x for x in scrape_responses if x]

    tasks = [asyncio.ensure_future(generate_ratings_operations(response, send_to_db=store_in_db, return_unrated=return_unrated)) for response in scrape_responses]
    parse_responses = await asyncio.gather(*tasks)

    if not store_in_db:
        return list(chain.from_iterable(list(chain.from_iterable(parse_responses))))

    upsert_ratings_operations, upsert_movies_operations = zip(*parse_responses)
    return list(chain.from_iterable(upsert_ratings_operations)), list(chain.from_iterable(upsert_movies_operations))

async def get_ratings(usernames, db_cursor=None, mongo_db=None, store_in_db=True):
    ratings_collection = mongo_db.ratings
    movies_collection = mongo_db.movies

    chunk_size = 10
    total_chunks = math.ceil(len(usernames) / chunk_size)

    for chunk_index in range(total_chunks):
        tasks = []
        db_ratings_operations = []
        db_movies_operations = []

        start_index = chunk_size * chunk_index
        end_index = min(start_index + chunk_size, len(usernames))
        username_chunk = usernames[start_index:end_index]

        for username in username_chunk:
            task = asyncio.ensure_future(
                get_user_ratings(
                    username,
                    db_cursor=db_cursor,
                    mongo_db=mongo_db,
                    store_in_db=store_in_db,
                )
            )
            tasks.append(task)

        user_responses = await asyncio.gather(*tasks)
        for response in user_responses:
            db_ratings_operations.extend(response[0])
            db_movies_operations.extend(response[1])

        if store_in_db:
            try:
                if db_ratings_operations:
                    ratings_collection.bulk_write(db_ratings_operations, ordered=False)

                if db_movies_operations:
                    movies_collection.bulk_write(db_movies_operations, ordered=False)

            except BulkWriteError as bwe:
                pprint(bwe.details)

def print_status(start, chunk_size, chunk_index, total_operations, total_records):
    total_time = round((time.time() - start), 2)
    completed_records = chunk_size * chunk_index
    time_per_user = round(total_time / completed_records, 2)
    remaining_estimate = round(time_per_user * (total_records - completed_records), 2)

    print("\n================")
    print(f"Users Complete: {completed_records}")
    print(f"Users Remaining: {(total_records - completed_records)}")
    print("Chunk Database Operations:", total_operations)
    print()
    print("Current Time/User:", f"{time_per_user} seconds")
    print("Elapsed Time:", helpers.format_seconds(total_time))
    print("Est. Time Remaining:", helpers.format_seconds(remaining_estimate))
    print("================\n")

async def main_async():
    db_name, client, tmdb_key = connect_to_db()
    db = client[db_name]
    users = db.users

    all_users = list(users.find({}).sort("last_updated", -1).limit(1200))
    all_usernames = [x["username"] for x in all_users]

    large_chunk_size = 100
    num_chunks = math.ceil(len(all_usernames) / large_chunk_size)

    pbar = tqdm(range(num_chunks))
    for chunk in pbar:
        pbar.set_description(f"Scraping ratings data for user group {chunk+1} of {num_chunks}")
        username_set = all_usernames[chunk * large_chunk_size: (chunk + 1) * large_chunk_size]

        await get_page_counts(username_set, users)
        await get_ratings(username_set, users, db)

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()