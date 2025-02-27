import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from bs4 import BeautifulSoup
from pymongo import UpdateOne, ReplaceOne
from pymongo.errors import BulkWriteError
import requests
import asyncio
import datetime
from pprint import pprint

from db.db_connect import connect_to_db
from scraping.get_ratings import get_user_ratings


def get_page_count(username):
    """Obtém o número de páginas de avaliações de um usuário."""
    url = f"https://letterboxd.com/{username}/films/by/date"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "lxml")

    body = soup.find("body")

    try:
        if "error" in body["class"]:
            return -1, None
    except KeyError:
        print(body)
        return -1, None

    try:
        page_link = soup.findAll("li", attrs={"class": "paginate-page"})[-1]
        num_pages = int(page_link.find("a").text.replace(",", ""))
        display_name = (
            body.find("section", attrs={"class": "profile-header"})
            .find("h1", attrs={"class": "title-3"})
            .text.strip()
        )
    except IndexError:
        num_pages = 1
        display_name = None

    return num_pages, display_name


def get_user_data(username, data_opt_in=False):
    """Coleta as avaliações do usuário e as insere no banco de dados, se necessário."""
    num_pages, display_name = get_page_count(username)

    if num_pages == -1:
        return [], "user_not_found"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    future = asyncio.ensure_future(
        get_user_ratings(
            username,
            db_cursor=None,
            mongo_db=None,
            store_in_db=False,
            num_pages=num_pages,
            return_unrated=True,
        )
    )
    loop.run_until_complete(future)

    user_ratings = [x for x in future.result() if x["rating_val"] >= 0]
    if data_opt_in:
        send_to_db(username, display_name, user_ratings=user_ratings)

    return future.result(), "success"


def send_to_db(username, display_name, user_ratings):
    """Insere ou atualiza as avaliações do usuário no MongoDB."""
    # Conecta ao MongoDB usando a função de conexão de db_connect.py
    db_name, client, tmdb_key = connect_to_db()  # Desempacota a tupla
    db = client[db_name]  # Acesse o banco de dados usando o client e db_name
    users = db.users  # Coleção 'users'
    ratings = db.ratings  # Coleção 'ratings'
    movies = db.movies  # Coleção 'movies'

    user = {
        "username": username,
        "display_name": display_name,
        "num_reviews": len(user_ratings),
        "last_updated": datetime.datetime.now(),
    }

    # Atualiza ou insere os dados do usuário
    users.update_one({"username": user["username"]}, {"$set": user}, upsert=True)

    # Prepara operações de upsert para avaliações e filmes
    upsert_ratings_operations = []
    upsert_movies_operations = []
    for rating in user_ratings:
        upsert_ratings_operations.append(
            ReplaceOne(
                {"user_id": username, "movie_id": rating["movie_id"]},
                rating,
                upsert=True,
            )
        )
        upsert_movies_operations.append(
            UpdateOne(
                {"movie_id": rating["movie_id"]},
                {"$set": {"movie_id": rating["movie_id"]}},
                upsert=True,
            )
        )

    # Executa operações em lote para otimizar inserção e atualização
    try:
        if upsert_ratings_operations:
            ratings.bulk_write(upsert_ratings_operations, ordered=False)
        if upsert_movies_operations:
            movies.bulk_write(upsert_movies_operations, ordered=False)
    except BulkWriteError as bwe:
        pprint(bwe.details)



if __name__ == "__main__":
    username = "wiped_issues"
    get_user_data(username, data_opt_in=True)
