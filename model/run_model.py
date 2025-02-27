import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from collections import defaultdict
from surprise import Dataset, SVD, Reader, dump
from surprise.model_selection import GridSearchCV
import pickle
import pandas as pd
import random
import pymongo
import pickle

try:
    from db.db_config import config
except ImportError:
    config = None

def get_top_n(predictions, n=20):
    """
    Get the top N recommendations from the prediction list.

    Parameters:
        predictions (list): List of predictions.
        n (int): Number of top recommendations to return.

    Returns:
        list: A list of top N recommendations.
    """
    top_n = [(iid, est) for _, iid, _, est, _ in predictions]
    top_n.sort(key=lambda x: x[1], reverse=True)  # Remove randomness
    return top_n[:n]


def run_model(username, algo, user_watched_list, threshold_movie_list, num_recommendations=20):
    """
    Run the recommendation model for a given user and return movie recommendations.

    Parameters:
        username (str): The username for whom to make recommendations.
        algo: The trained recommendation algorithm.
        user_watched_list (list): List of movies the user has watched.
        threshold_movie_list (list): List of all movies considered for recommendations.
        num_recommendations (int): Number of recommendations to generate.

    Returns:
        list: A list of recommended movies.
    """
    # Connect to MongoDB Client
    db_name = config["MONGO_DB"] if config else os.environ.get('MONGO_DB', '')
    
    if config and config["CONNECTION_URL"]:
        connection_url = config["CONNECTION_URL"]
    else:
        connection_url = os.environ.get('CONNECTION_URL', '')

    try:
        client = pymongo.MongoClient(connection_url, server_api=pymongo.server_api.ServerApi('1'))
        db = client[db_name]
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return []

    unwatched_movies = [x for x in threshold_movie_list if x not in user_watched_list]
    prediction_set = [(username, x, 0) for x in unwatched_movies]

    predictions = algo.test(prediction_set)
    top_n = get_top_n(predictions, num_recommendations)

    movie_fields = ["image_url", "movie_id", "movie_title", "year_released", "genres", "original_language", "popularity", "runtime", "release_date"]
    movie_data = {x["movie_id"]: {k: v for k, v in x.items() if k in movie_fields} for x in db.movies.movies.find({"movie_id": {"$in": [x[0] for x in top_n]}})}

    return_object = [{
        "movie_id": x[0],
        "predicted_rating": round(x[1], 3),
        "unclipped_rating": round(x[1], 3),
        "movie_data": movie_data[x[0]]
    } for x in top_n]

    for i, prediction in enumerate(return_object):
        if prediction['predicted_rating'] == 10:
            return_object[i]['unclipped_rating'] = float(algo.predict(username, prediction["movie_id"], clip=False).est)

    return_object.sort(key=lambda x: x["unclipped_rating"], reverse=True)
    return return_object


if __name__ == "__main__":
    with open("model/user_watched.txt", "rb") as fp:
        user_watched_list = pickle.load(fp)

    with open("model/threshold_movie_list.txt", "rb") as fp:
        threshold_movie_list = pickle.load(fp)

    algo = dump.load("model/mini_model.pkl")[1]

    recs = run_model("wiped_issues", algo, user_watched_list, threshold_movie_list, 25)
    print(recs)
