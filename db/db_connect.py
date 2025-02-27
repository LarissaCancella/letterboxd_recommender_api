from dotenv import load_dotenv
load_dotenv()  # Isso carrega as variáveis do arquivo .env

import os
import pymongo

def connect_to_db():
    """
    Conecta ao banco de dados MongoDB usando credenciais armazenadas no arquivo `db_config.py`
    (que está no `.gitignore`) ou, caso não esteja disponível, usando variáveis de ambiente.

    Retorna:
        db_name (str): Nome do banco de dados.
        client (MongoClient): Cliente MongoDB conectado.
        tmdb_key (str): Chave da API TMDB.
    """
    try:
        # Importa configuração local se disponível
        from db_config import config, tmdb_key

        db_name = config["MONGO_DB"]
        connection_url = config.get("CONNECTION_URL")
        
        # Constrói o cliente do MongoDB
        if connection_url:
            client = pymongo.MongoClient(connection_url, server_api=pymongo.server_api.ServerApi('1'))
        else:
            client = pymongo.MongoClient(
                f'mongodb+srv://{config["MONGO_USERNAME"]}:{config["MONGO_PASSWORD"]}@cluster0.{config["MONGO_CLUSTER_ID"]}.mongodb.net/{db_name}?retryWrites=true&w=majority'
            )

    except ModuleNotFoundError:
        # Se `db_config.py` não estiver disponível, usa variáveis de ambiente
        db_name = os.getenv('MONGO_DB')
        connection_url = os.getenv("CONNECTION_URL")
        tmdb_key = os.getenv('TMDB_KEY')
        
        # Verificação para garantir que as variáveis de ambiente estejam definidas
        if not db_name or not connection_url or not tmdb_key:
            raise EnvironmentError("Variáveis de ambiente necessárias para a conexão com o banco de dados estão ausentes.")

        client = pymongo.MongoClient(connection_url, server_api=pymongo.server_api.ServerApi('1'))

    return db_name, client, tmdb_key
