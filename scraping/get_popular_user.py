import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from pymongo.operations import UpdateOne
import requests
from bs4 import BeautifulSoup
import pymongo
from pymongo.errors import BulkWriteError
from pprint import pprint
from tqdm import tqdm
from time import sleep
import logging

from db.db_connect import connect_to_db

# Configuração do Logger
logging.basicConfig(level=logging.INFO)

# Conexão com MongoDB
db_name, client, tmdb_key = connect_to_db()
db = client[db_name]
users = db.users

# URL base e número de páginas
base_url = "https://letterboxd.com/members/popular/this/week/page/{}/"
total_pages = 128

def scrape_and_update_users(page):
    """Extrai dados de usuários populares e insere/atualiza no MongoDB."""
    try:
        r = requests.get(base_url.format(page))
        r.raise_for_status()  # Checa se a resposta foi bem-sucedida
        soup = BeautifulSoup(r.text, "html.parser")
        
        table = soup.find("table", attrs={"class": "person-table"})
        rows = table.findAll("td", attrs={"class": "table-person"})
        
        update_operations = []
        for row in rows:
            link = row.find("a")["href"]
            username = link.strip('/')
            display_name = row.find("a", attrs={"class": "name"}).text.strip()
            num_reviews = int(row.find("small").find("a").text.replace('\xa0', ' ').split()[0].replace(',', ''))

            user = {
                "username": username,
                "display_name": display_name,
                "num_reviews": num_reviews
            }

            update_operations.append(
                UpdateOne(
                    {"username": user["username"]},
                    {"$set": user},
                    upsert=True
                )
            )

        # Escreve em lote no MongoDB
        if update_operations:
            users.bulk_write(update_operations, ordered=False)
            logging.info(f"Usuários da página {page} inseridos/atualizados com sucesso.")

    except requests.RequestException as e:
        logging.error(f"Erro ao solicitar a página {page}: {e}")
    except BulkWriteError as bwe:
        logging.error("Erro no bulk_write:")
        pprint(bwe.details)

# Loop de scraping com barra de progresso e espera entre requests
pbar = tqdm(range(1, total_pages + 1))
for page in pbar:
    pbar.set_description(f"Scraping página {page} de {total_pages} dos usuários populares")
    scrape_and_update_users(page)
    sleep(1)  # Espera de 1 segundo entre requests
