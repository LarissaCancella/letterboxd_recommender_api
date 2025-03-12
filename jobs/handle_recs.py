import sys
import os
import logging

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import pandas as pd
import pickle
from rq import Queue, get_current_job
from rq.registry import FinishedJobRegistry
from scraping.get_user_ratings import get_user_data
from model.build_model import build_model
from model.run_model import run_model
from worker import conn


def get_previous_job_from_registry(index=-1):
    """
    Retrieve a previous job from the Redis finished job registry.
    
    Parameters:
        index (int): Index of the job in the registry, default is the last job.
    
    Returns:
        Job: The retrieved job object.
    """
    q = Queue('high', connection=conn)
    registry = FinishedJobRegistry(queue=q)
    try:
        job_id = registry.get_job_ids()[index]
        return q.fetch_job(job_id)
    except IndexError:
        print("No jobs found in registry.")
        return None


def filter_threshold_list(threshold_movie_list, review_count_threshold=2000):
    """
    Filter movies that have review counts below a specified threshold.
    
    Parameters:
        threshold_movie_list (list): List of movie IDs that passed the initial threshold.
        review_count_threshold (int): Maximum review count for filtering movies.
    
    Returns:
        list: Filtered list of movie IDs.
    """
    try:
        review_counts = pd.read_csv('data_processing/data/review_counts.csv')
    except FileNotFoundError:
        print("Review counts file not found.")
        return threshold_movie_list

    review_counts = review_counts.loc[review_counts['count'] < review_count_threshold]
    included_movies = review_counts['movie_id'].to_list()
    return [x for x in threshold_movie_list if x in included_movies]


def get_client_user_data(username, data_opt_in):
    """
    Retrieve and save user data and status metadata for the current job.
    
    Parameters:
        username (str): Username of the client.
        data_opt_in (bool): Indicates if the client opted in to data sharing.
    
    Returns:
        list: List of user's movie ratings.
    """
    logger.info(f"Iniciando get_client_user_data para {username}")
    try:
        user_data = get_user_data(username, data_opt_in)
        current_job = get_current_job(conn)
        if current_job:
            current_job.meta['user_status'] = user_data[1]
            current_job.meta['num_user_ratings'] = len(user_data[0])
            current_job.save()
        return user_data[0]
    except Exception as e:
        logger.error(f"Erro em get_client_user_data para {username}: {str(e)}")
        raise


def build_client_model(username, training_data_rows=200000, popularity_threshold=None, num_items=30):
    """
    Build a recommendation model for the client and generate movie recommendations.
    
    Parameters:
        username (str): Username for whom the model is being built.
        training_data_rows (int): Number of rows for the training dataset sample.
        popularity_threshold (int): Threshold for filtering popular movies (optional).
        num_items (int): Number of recommendations to generate.
    
    Returns:
        list: List of movie recommendations.
    """
    # Load user data from previous Redis job
    logger.info(f"Iniciando build_client_model para {username}")
    try:
        current_job = get_current_job(conn)
        user_data = current_job.dependency.result if current_job and current_job.dependency else []

        if current_job:
            current_job.meta['stage'] = 'creating_sample_data'
            current_job.save()

        # Load training data and sample it
        try:
            df = pd.read_csv('data/ratings.csv')
        except FileNotFoundError:
            print("Training data file not found.")
            return []
        
        model_df = df.head(training_data_rows)

        # Load threshold movie list
        try:
            with open("model/threshold_movie_list.txt", "rb") as fp:
                threshold_movie_list = pickle.load(fp)
        except FileNotFoundError:
            print("Threshold movie list file not found.")
            return []

        # Apply popularity filter if specified
        if popularity_threshold:
            threshold_movie_list = filter_threshold_list(threshold_movie_list, popularity_threshold)
        
        # Build and run the model
        if current_job:
            current_job.meta['stage'] = 'building_model'
            current_job.save()
        
        algo, user_watched_list = build_model(model_df, user_data)
        
        if current_job:
            current_job.meta['stage'] = 'running_model'
            current_job.save()
        
        recs = run_model(username, algo, user_watched_list, threshold_movie_list, num_items)
        logger.info(f"Finalizando build_client_model para {username}")
        return recs
    except Exception as e:
        logger.error(f"Erro em build_client_model para {username}: {str(e)}")
        raise