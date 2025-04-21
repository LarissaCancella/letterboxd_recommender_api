import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import pandas as pd
import pickle
import pymongo

from db.db_connect import connect_to_db

def get_sample(cursor, iteration_size):
    """
    Fetches a random sample of ratings from the MongoDB collection.

    Parameters:
        cursor (Collection): The MongoDB collection to sample from.
        iteration_size (int): The size of the sample to fetch.

    Returns:
        list: A list of sampled ratings.
    """
    while True:
        try:
            rating_cursor = cursor.aggregate([{"$sample": {"size": iteration_size}}])
            # Converte o cursor para lista antes de qualquer operação de print
            rating_sample = list(rating_cursor)
            print("Obtained sample size:", len(rating_sample))
            return rating_sample
        except pymongo.errors.OperationFailure:
            print("Encountered $sample operation error. Retrying...")

def get_sample_for_atlas_free(cursor, iteration_size):
    """
    Otimizado especificamente para MongoDB Atlas na camada gratuita.
    Usa tamanhos de lote extremamente pequenos e múltiplos métodos.
    """
    import time
    import random
    
    results = []
    print(f"Iniciando amostragem para obter {iteration_size} registros no MongoDB Atlas Free Tier")
    
    # Método 1: Várias chamadas $sample com tamanhos muito pequenos
    max_batch_size = 200  # Extremamente pequeno para Atlas Free
    attempts = 0
    max_attempts = 30
    
    while len(results) < iteration_size and attempts < max_attempts:
        try:
            # Calcula quantos registros ainda precisamos
            remaining = iteration_size - len(results)
            batch_size = min(max_batch_size, remaining)
            
            print(f"Tentativa {attempts+1}: buscando {batch_size} registros via $sample...")
            
            # Executa a agregação com timeout explícito baixo
            pipeline = [{"$sample": {"size": batch_size}}]
            batch_cursor = cursor.aggregate(
                pipeline,
                allowDiskUse=True,  # Permitir uso de disco
                maxTimeMS=5000      # Timeout de 5 segundos
            )
            
            batch_result = list(batch_cursor)
            
            if batch_result:
                print(f"Obtidos {len(batch_result)} registros neste lote")
                results.extend(batch_result)
                
                # Pausa entre chamadas para não sobrecarregar o Atlas
                time.sleep(1)
            else:
                print("Lote vazio retornado")
                
            attempts += 1
            
        except pymongo.errors.OperationFailure as e:
            print(f"Erro na operação $sample: {str(e)}")
            # Reduz ainda mais o tamanho do lote após cada erro
            max_batch_size = max(50, max_batch_size // 2)
            print(f"Reduzindo tamanho do lote para {max_batch_size}")
            attempts += 1
            time.sleep(2)  # Pausa maior após um erro
            
            # Se continuamos tendo erros com lotes pequenos, tente outro método
            if max_batch_size <= 50 or attempts >= 10:
                break
                
    # Método 2: Amostragem aleatória usando skip
    if len(results) < iteration_size:
        print(f"Alternando para método de amostragem com skip aleatório")
        
        try:
            # Tentativa de obter a contagem aproximada
            try:
                total_count = cursor.estimated_document_count()
            except:
                # Fallback para contagem mais lenta mas segura
                total_count = cursor.count_documents({})
                
            print(f"Total estimado de documentos: {total_count}")
            
            batch_size = 50  # Muito pequeno para evitar problemas
            skip_attempts = 0
            max_skip_attempts = 50
            
            while len(results) < iteration_size and skip_attempts < max_skip_attempts:
                try:
                    # Gera um índice aleatório para skip
                    skip_index = random.randint(0, max(0, total_count - batch_size - 1))
                    
                    # Adiciona um filtro simples para melhorar performance
                    # Você pode ajustar isso com base na sua estrutura de dados
                    filter_query = {}
                    
                    docs = cursor.find(filter_query).limit(batch_size).skip(skip_index)
                    batch = list(docs)
                    
                    if batch:
                        print(f"Obtidos {len(batch)} registros via skip ({skip_index})")
                        results.extend(batch)
                    
                    skip_attempts += 1
                    time.sleep(0.5)  # Pequena pausa entre consultas
                    
                except Exception as skip_error:
                    print(f"Erro no método skip: {str(skip_error)}")
                    time.sleep(1)
                    skip_attempts += 1
        
        except Exception as count_error:
            print(f"Erro ao calcular contagem: {str(count_error)}")
    
    # Método 3: Busca por gamas de valores (se aplicável)
    if len(results) < iteration_size:
        print(f"Tentando método de gama de valores...")
        try:
            # Este método assume que você tem algum campo numérico ou data
            # Substitua "rating_val" pelo campo apropriado no seu schema
            ranges = [
                {"$match": {"rating_val": {"$gte": 1, "$lt": 2}}},
                {"$match": {"rating_val": {"$gte": 2, "$lt": 3}}},
                {"$match": {"rating_val": {"$gte": 3, "$lt": 4}}},
                {"$match": {"rating_val": {"$gte": 4, "$lt": 5}}},
                {"$match": {"rating_val": {"$gte": 5}}}
            ]
            
            for range_query in ranges:
                if len(results) >= iteration_size:
                    break
                    
                try:
                    # Limita a apenas alguns documentos por faixa
                    pipeline = [
                        range_query,
                        {"$limit": 100}
                    ]
                    
                    range_cursor = cursor.aggregate(pipeline, maxTimeMS=3000)
                    range_results = list(range_cursor)
                    
                    if range_results:
                        print(f"Obtidos {len(range_results)} registros via gama de valores")
                        results.extend(range_results)
                        
                    time.sleep(0.5)
                    
                except Exception as range_error:
                    print(f"Erro na consulta de gama: {str(range_error)}")
        
        except Exception as e:
            print(f"Erro no método de gama: {str(e)}")
    
    print(f"Total coletado após todos os métodos: {len(results)} registros")
    
    # Remove duplicatas (pode ocorrer com métodos diferentes)
    unique_doc_ids = set()
    unique_results = []
    
    for doc in results:
        # Usa o ID do MongoDB como identificador único
        doc_id = str(doc.get("_id", ""))
        if doc_id and doc_id not in unique_doc_ids:
            unique_doc_ids.add(doc_id)
            unique_results.append(doc)
    
    print(f"Total após remoção de duplicatas: {len(unique_results)} registros")
    return unique_results[:iteration_size]

def create_training_data(db_client, sample_size=20000):  # Reduzido para 20,000
    """
    Creates training data by sampling user ratings from the database.

    Parameters:
        db_client (MongoClient): The MongoDB client instance.
        sample_size (int): The target size of unique ratings to collect.

    Returns:
        DataFrame: A DataFrame containing user ratings for training.
    """
    print("Gerando dados de treinamento com MongoDB Atlas Free Tier")
    print(f"Tamanho de amostra alvo: {sample_size} registros")
    
    ratings = db_client.ratings
    all_ratings = []
    unique_pairs = set()
    
    # Para Atlas Free, fazemos em lotes menores e com mais tentativas
    batch_sizes = [2000, 3000, 5000]  # Começando com lotes bem pequenos
    
    for batch_size in batch_sizes:
        if len(all_ratings) >= sample_size:
            break
        
        print(f"Tentando obter lote de {batch_size} registros...")
        try:
            # Usa a função específica para Atlas Free
            rating_sample = get_sample_for_atlas_free(ratings, batch_size)
            
            # Processar apenas registros únicos
            for item in rating_sample:
                unique_key = (item.get("movie_id", ""), item.get("user_id", ""))
                
                if unique_key not in unique_pairs and all(k in item for k in ["user_id", "movie_id", "rating_val"]):
                    unique_pairs.add(unique_key)
                    all_ratings.append({
                        "user_id": item["user_id"],
                        "movie_id": item["movie_id"],
                        "rating_val": item["rating_val"]
                    })
            
            print(f"Total acumulado: {len(all_ratings)}/{sample_size}")
            
        except Exception as e:
            print(f"Erro no processamento do lote: {str(e)}")
            print("Continuando com próximo tamanho de lote...")
    
    print(f"Coleta finalizada com {len(all_ratings)} ratings únicos")
    
    # Converte para DataFrame
    if all_ratings:
        df = pd.DataFrame(all_ratings)
        return df
    else:
        print("AVISO: Nenhum rating coletado!")
        return pd.DataFrame(columns=["user_id", "movie_id", "rating_val"])


def create_movie_data_sample(db_client, movie_list):
    """
    Creates a DataFrame sample of movies based on a provided list.

    Parameters:
        db_client (MongoClient): The MongoDB client instance.
        movie_list (list): A list of movie IDs to include in the sample.

    Returns:
        DataFrame: A DataFrame containing movie data.
    """
    movies_cursor = db_client.movies.find({"movie_id": {"$in": movie_list}})
    movie_df = pd.DataFrame(list(movies_cursor))
    
    movie_df = movie_df[["movie_id", "image_url", "movie_title", "year_released"]]
    movie_df["image_url"] = movie_df["image_url"].fillna("").replace(
        [
            "https://a.ltrbxd.com/resized/",
            "https://s.ltrbxd.com/static/img/empty-poster-230.c6baa486.png"
        ], 
        ["", ""]
    )

    return movie_df


if __name__ == "__main__":
    # Connect to MongoDB client
    db_name, client, tmdb_key = connect_to_db()
    db = client[db_name]

    min_review_threshold = 20

    # Generate training data sample
    print("Generate training data sample")
    training_df = create_training_data(db, 60000)
    print("finished generating")

    # Create review counts dataframe
    review_count = db.ratings.aggregate(
        [
            {"$group": {"_id": "$movie_id", "review_count": {"$sum": 1}}},
            {"$match": {"review_count": {"$gte": min_review_threshold}}},
        ]
    )
    review_counts_df = pd.DataFrame(list(review_count))
    review_counts_df.rename(columns={"_id": "movie_id", "review_count": "count"}, inplace=True)

    threshold_movie_list = review_counts_df["movie_id"].to_list()

    # Generate movie data CSV
    movie_df = create_movie_data_sample(db, threshold_movie_list)
    
    retain_list = movie_df.loc[
        (movie_df["year_released"].notna() & movie_df["year_released"] != 0.0)
    ]["movie_id"].to_list()

    threshold_movie_list = [x for x in threshold_movie_list if x in retain_list]

    # Store Data
    with open("model/threshold_movie_list.txt", "wb") as fp:
        pickle.dump(threshold_movie_list, fp)

    training_df.to_csv("./data/training_data.csv", index=False)
    review_counts_df.to_csv("./data/review_counts.csv", index=False)
    movie_df.to_csv("./data/movie_data.csv", index=False)
