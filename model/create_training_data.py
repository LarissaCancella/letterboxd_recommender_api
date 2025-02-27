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
            rating_sample = cursor.aggregate([{"$sample": {"size": iteration_size}}])
            print("rating_sample: ", rating_sample)
            return list(rating_sample)
        except pymongo.errors.OperationFailure:
            print("Encountered $sample operation error. Retrying...")


def create_training_data(db_client, sample_size=200000):
    """
    Creates training data by sampling user ratings from the database.

    Parameters:
        db_client (MongoClient): The MongoDB client instance.
        sample_size (int): The target size of unique ratings to collect.

    Returns:
        DataFrame: A DataFrame containing user ratings for training.
    """
    ratings = db_client.ratings
    all_ratings = []
    unique_records = 0
    
    #print("ratings: ", ratings)

    while unique_records < sample_size:
        rating_sample = get_sample(ratings, 100000)
        all_ratings += rating_sample
        #unique_records = len(set((x["movie_id"], x["user_id"]) for x in all_ratings))
        unique_records = len(set([(x["movie_id"] + x["user_id"]) for x in all_ratings]))
        print(unique_records)
        print(sample_size)
        print(unique_records < sample_size)

    print("finished while")
    #df = pd.DataFrame(all_ratings)
    #df = df[["user_id", "movie_id", "rating_val"]].drop_duplicates().head(sample_size)

    df = pd.DataFrame(all_ratings)
    df = df[["user_id", "movie_id", "rating_val"]]
    df.drop_duplicates(inplace=True)
    df = df.head(sample_size)

    #print(df.head())
    return df


def create_movie_data_sample(db_client, movie_list):
    """
    Creates a DataFrame sample of movies based on a provided list.

    Parameters:
        db_client (MongoClient): The MongoDB client instance.
        movie_list (list): A list of movie IDs to include in the sample.

    Returns:
        DataFrame: A DataFrame containing movie data.
    """
    movies_cursor = db_client.movies.movies.find({"movie_id": {"$in": movie_list}})
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
    print(threshold_movie_list)

    # Generate movie data CSV
    movie_df = create_movie_data_sample(db, threshold_movie_list)
    #print(movie_df.head())
    #print(movie_df.shape)
    print(movie_df)

    # Use movie_df to filter out items without a valid "year_released"
    #retain_list = movie_df[movie_df["year_released"].notna() & (movie_df["year_released"] != 0.0)]["movie_id"].to_list()
    
    retain_list = movie_df.loc[
        (movie_df["year_released"].notna() & movie_df["year_released"] != 0.0)
    ]["movie_id"].to_list()
    print("retain list", retain_list)

    threshold_movie_list = [x for x in threshold_movie_list if x in retain_list]
    print("-- threshold_movie_list --", threshold_movie_list)

    # Store Data
    with open("model/threshold_movie_list.txt", "wb") as fp:
        pickle.dump(threshold_movie_list, fp)

    training_df.to_csv("./data/training_data.csv", index=False)
    review_counts_df.to_csv("./data/review_counts.csv", index=False)
    movie_df.to_csv("./data/movie_data.csv", index=False)
