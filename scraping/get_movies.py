import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import datetime
from bs4 import BeautifulSoup
import asyncio
from aiohttp import ClientSession
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError
from tqdm import tqdm

from db.db_connect import connect_to_db

async def fetch_letterboxd(url, session, input_data={}):
    async with session.get(url) as r:
        response = await r.read()

        soup = BeautifulSoup(response, "lxml")

        #movie_header = soup.find('section', attrs={'id': 'featured-film-header'})
        movie_header = soup.find('section', attrs={'class': 'film-header-group'})

        #movie_title = movie_header.find('h1').text if movie_header else ''
        #year = int(movie_header.find('small', attrs={'class': 'number'}).find('a').text) if movie_header else None

        if movie_header:
            # Extrai o título do filme
            title_element = movie_header.find('h1', attrs={'class': 'headline-1 filmtitle'})
            movie_title = title_element.find('span', attrs={'class': 'name'}).text.strip() if title_element else ''
            print(movie_title)

            # Extrai o ano do filme
            year_element = movie_header.find('div', attrs={'class': 'releaseyear'})
            year = int(year_element.find('a').text.strip()) if year_element else None
            print(year)
        else:
            movie_title = ''
            year = None

        soup.find("span", attrs={"class": "rating"})
        # Fetch IMDb and TMDb IDs
        imdb_link, imdb_id = extract_imdb_data(soup)
        tmdb_link, tmdb_id = extract_tmdb_data(soup)

        movie_object = {
            "movie_id": input_data["movie_id"],
            "movie_title": movie_title,
            "year_released": year,
            "imdb_link": imdb_link,
            "tmdb_link": tmdb_link,
            "imdb_id": imdb_id,
            "tmdb_id": tmdb_id
        }

        return UpdateOne({"movie_id": input_data["movie_id"]}, {"$set": movie_object}, upsert=True)

def extract_imdb_data(soup):
    try:
        imdb_link = soup.find("a", attrs={"data-track-action": "IMDb"})['href']
        imdb_id = imdb_link.split('/title')[1].strip('/').split('/')[0]
    except (TypeError, IndexError):
        return '', ''
    return imdb_link, imdb_id

def extract_tmdb_data(soup):
    try:
        tmdb_link = soup.find("a", attrs={"data-track-action": "TMDb"})['href']
        tmdb_id = tmdb_link.split('/movie')[1].strip('/').split('/')[0]
    except (TypeError, IndexError):
        return '', ''
    return tmdb_link, tmdb_id

async def fetch_poster(url, session, input_data={}):
    async with session.get(url) as r:
        response = await r.read()
        soup = BeautifulSoup(response, "lxml")
        
        image_url = extract_image_url(soup)
        movie_object = {"movie_id": input_data["movie_id"], "last_updated": datetime.datetime.now()}
        
        if image_url:
            movie_object["image_url"] = image_url
        
        return UpdateOne({"movie_id": input_data["movie_id"]}, {"$set": movie_object}, upsert=True)

def extract_image_url(soup):
    try:
        image_url = soup.find('div', attrs={'class': 'film-poster'}).find('img')['src'].split('?')[0]
        if 'https://s.ltrbxd.com/static/img/empty-poster' in image_url:
            return ''
        return image_url.replace('https://a.ltrbxd.com/resized/', '').split('.jpg')[0]
    except AttributeError:
        return ''

async def fetch_tmdb_data(url, session, movie_data, input_data={}):
    async with session.get(url) as r:
        response = await r.json()
        movie_object = movie_data
        
        # Extract fields from TMDb data
        object_fields = ["genres", "production_countries", "spoken_languages"]
        for field_name in object_fields:
            movie_object[field_name] = [x["name"] for x in response.get(field_name, [])]

        simple_fields = ["popularity", "overview", "runtime", "vote_average", "vote_count", "release_date", "original_language"]
        for field_name in simple_fields:
            movie_object[field_name] = response.get(field_name)

        movie_object['last_updated'] = datetime.datetime.now()
        
        return UpdateOne({"movie_id": input_data["movie_id"]}, {"$set": movie_object}, upsert=True)

async def get_movies(movie_list, mongo_db):
    url = "https://letterboxd.com/film/{}/"
    async with ClientSession() as session:
        tasks = [asyncio.ensure_future(fetch_letterboxd(url.format(movie), session, {"movie_id": movie})) for movie in movie_list]
        upsert_operations = await asyncio.gather(*tasks)
        await bulk_write_operations(mongo_db.movies, upsert_operations)

async def get_movie_posters(movie_list, mongo_db):
    url = "https://letterboxd.com/ajax/poster/film/{}/hero/230x345"
    async with ClientSession() as session:
        tasks = [asyncio.ensure_future(fetch_poster(url.format(movie), session, {"movie_id": movie})) for movie in movie_list]
        upsert_operations = await asyncio.gather(*tasks)
        await bulk_write_operations(mongo_db.movies, upsert_operations)

async def get_rich_data(movie_list, mongo_db, tmdb_key):
    base_url = "https://api.themoviedb.org/3/movie/{}?api_key={}"
    async with ClientSession() as session:
        tasks = [
            asyncio.ensure_future(fetch_tmdb_data(base_url.format(movie["tmdb_id"], tmdb_key), session, movie, {"movie_id": movie["movie_id"]}))
            for movie in movie_list if movie['tmdb_id']
        ]
        upsert_operations = await asyncio.gather(*tasks)
        await bulk_write_operations(mongo_db.movies, upsert_operations)

async def bulk_write_operations(collection, operations):
    try:
        if operations:
            collection.bulk_write(operations, ordered=False)
    except BulkWriteError as bwe:
        pprint(bwe.details)

async def main(data_type="letterboxd"):
    db_name, client, tmdb_key = connect_to_db()
    db = client[db_name]
    movies = db.movies

    if data_type == "letterboxd":
        newly_added = [x['movie_id'] for x in movies.find({"tmdb_id": {"$exists": False}})]
        needs_update = [x['movie_id'] for x in movies.find({"tmdb_id": {"$exists": True}}).sort("last_updated", -1).limit(6000)]
        all_movies = needs_update + newly_added
    elif data_type == "poster":
        two_months_ago = datetime.datetime.now() - datetime.timedelta(days=60)
        all_movies = [x['movie_id'] for x in movies.find({"$or": [{"image_url": {"$exists": False}}, {"last_updated": {"$lte": two_months_ago}}]})]
    else:
        all_movies = [x for x in movies.find({"genres": {"$exists": False}, "tmdb_id": {"$ne": ""}, "tmdb_id": {"$exists": True}})]

    loop = asyncio.get_event_loop()
    chunk_size = 12
    num_chunks = len(all_movies) // chunk_size + 1

    print("Total Movies to Scrape:", len(all_movies))
    print('Total Chunks:', num_chunks)
    print("=======================\n")

    pbar = tqdm(range(num_chunks))
    for chunk_i in pbar:
        pbar.set_description(f"Scraping chunk {chunk_i + 1} of {num_chunks}")
        chunk = all_movies[chunk_i * chunk_size: (chunk_i + 1) * chunk_size] if chunk_i < num_chunks - 1 else all_movies[chunk_i * chunk_size:]

        for attempt in range(5):
            try:
                if data_type == "letterboxd":
                    await get_movies(chunk, movies)
                elif data_type == "poster":
                    await get_movie_posters(chunk, movies)
                else:
                    await get_rich_data(chunk, movies, tmdb_key)
                break
            except Exception as e:
                print(f"Error: {e}")
                print(f"Error on attempt {attempt + 1}, retrying...")

        else:
            print(f"Could not complete requests for chunk {chunk_i + 1}")

# Use asyncio.run para executar a função main
if __name__ == "__main__":
    asyncio.run(main("letterboxd"))
    asyncio.run(main("poster"))
    asyncio.run(main("tmdb"))

