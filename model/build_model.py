import sys
import os

# Adiciona o diretório raiz do projeto ao Python Path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import pandas as pd
import pickle
from surprise import Dataset, Reader, SVD
from surprise.dump import dump

import numpy as np

def build_model(df, user_data):
    """
    Builds a recommendation model using SVD algorithm on the provided ratings data.

    Parameters:
        df (DataFrame): The DataFrame containing user ratings.
        user_data (list): A list of user ratings data.

    Returns:
        algo (SVD): The trained SVD model.
        user_watched_list (list): A list of movie IDs that the user has watched.
    """
    # Set a fixed random seed for reproducibility
    np.random.seed(12)

    # Filter out user ratings with non-zero values
    user_rated = [x for x in user_data if x['rating_val'] > 0]
    user_df = pd.DataFrame(user_rated)

    # Combine the original DataFrame with user data
    combined_df = pd.concat([df, user_df]).drop_duplicates().reset_index(drop=True)

    # Surprise dataset loading
    reader = Reader(rating_scale=(1, 10))
    data = Dataset.load_from_df(combined_df[["user_id", "movie_id", "rating_val"]], reader)

    # Configure and train the SVD algorithm
    algo = SVD()
    training_set = data.build_full_trainset()
    algo.fit(training_set)

    # Extract the list of movies watched by the user
    user_watched_list = [x['movie_id'] for x in user_data]

    return algo, user_watched_list

if __name__ == "__main__":
    import os
    from scraping.get_user_ratings import get_user_data

    # Load ratings data
    df = pd.read_csv('data/ratings.csv')

    user_data = get_user_data("wiped_issues")[0]
    algo, user_watched_list = build_model(df, user_data)

    # Save the model and user watched list
    try:
        dump("model/mini_model.pkl", predictions=None, algo=algo, verbose=1)
        with open("model/user_watched.txt", "wb") as fp:
            pickle.dump(user_watched_list, fp)
    except Exception as e:
        print(f"An error occurred while saving the model: {e}")
