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
from pprint import pprint

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
            "tmdb_id": tmdb_id,
            "last_updated": datetime.datetime.now()
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
            for movie in movie_list if movie.get('tmdb_id')
        ]
        upsert_operations = await asyncio.gather(*tasks)
        await bulk_write_operations(mongo_db.movies, upsert_operations)

async def bulk_write_operations(collection, operations):
    try:
        if operations:
            collection.bulk_write(operations, ordered=False)
    except BulkWriteError as bwe:
        pprint(bwe.details)

async def process_movies(movie_list, movies_collection, data_type, tmdb_key):
    if not movie_list:
        print(f"Nenhum filme para processar do tipo: {data_type}")
        return
    
    print(f"Total de filmes para processar ({data_type}): {len(movie_list)}")
    chunk_size = 12
    num_chunks = len(movie_list) // chunk_size + 1
    
    print('Total Chunks:', num_chunks)
    print("=======================\n")
    
    pbar = tqdm(range(num_chunks))
    for chunk_i in pbar:
        pbar.set_description(f"Processando chunk {chunk_i + 1} de {num_chunks}")
        chunk = movie_list[chunk_i * chunk_size: (chunk_i + 1) * chunk_size] if chunk_i < num_chunks - 1 else movie_list[chunk_i * chunk_size:]
        
        for attempt in range(5):
            try:
                if data_type == "letterboxd":
                    await get_movies(chunk, movies_collection)
                elif data_type == "poster":
                    await get_movie_posters(chunk, movies_collection)
                else:
                    await get_rich_data(chunk, movies_collection, tmdb_key)
                break
            except Exception as e:
                print(f"Erro: {e}")
                print(f"Erro na tentativa {attempt + 1}, tentando novamente...")
        else:
            print(f"Não foi possível completar as requisições para o chunk {chunk_i + 1}")

async def main():
    db_name, client, tmdb_key = connect_to_db()
    db = client[db_name]
    movies = db.movies
    
    # Define estratégia de atualização baseada em tempo
    two_months_ago = datetime.datetime.now() - datetime.timedelta(days=60)
    
    # Passo 1: Obter dados básicos do Letterboxd
    print("\n=== Processando dados do Letterboxd ===")
    
    # Filmes que nunca foram processados (sem tmdb_id)
    newly_added = list(movies.find({"tmdb_id": {"$exists": False}}, {"movie_id": 1}))
    newly_added_ids = [x['movie_id'] for x in newly_added]
    print(f"Filmes novos encontrados: {len(newly_added_ids)}")
    
    # Filmes que precisam de atualização (antigos, última atualização há mais de 60 dias)
    needs_update = list(movies.find(
        {"tmdb_id": {"$exists": True}, "last_updated": {"$lt": two_months_ago}},
        {"movie_id": 1}
    ).sort("last_updated", 1))  # Ordena do mais antigo para o mais recente
    needs_update_ids = [x['movie_id'] for x in needs_update]
    print(f"Filmes que precisam de atualização: {len(needs_update_ids)}")
    
    # Combina as listas, priorizando filmes novos
    letterboxd_movies = newly_added_ids + needs_update_ids
    await process_movies(letterboxd_movies, db, "letterboxd", tmdb_key)
    
    # Passo 2: Obter posters para filmes que não os têm ou que precisam de atualização
    print("\n=== Processando posters ===")
    poster_movies = list(movies.find(
        {"$or": [
            {"image_url": {"$exists": False}},
            {"image_url": ""},
            {"image_url": {"$exists": True}, "last_updated": {"$lt": two_months_ago}}
        ]},
        {"movie_id": 1}
    ))
    poster_movie_ids = [x['movie_id'] for x in poster_movies]
    await process_movies(poster_movie_ids, db, "poster", tmdb_key)
    
    # Passo 3: Obter dados TMDB para filmes que têm tmdb_id mas não têm dados completos
    print("\n=== Processando dados do TMDB ===")
    tmdb_movies = list(movies.find(
        {"genres": {"$exists": False}, "tmdb_id": {"$ne": ""}, "tmdb_id": {"$exists": True}},
        {"movie_id": 1, "tmdb_id": 1}
    ))
    await process_movies(tmdb_movies, db, "tmdb", tmdb_key)

# Use asyncio.run para executar a função main
if __name__ == "__main__":
    asyncio.run(main())