echo "======================================================="
echo "Scraping popular users from site and adding to database"
echo "======================================================="
pipenv run python ./scraping/get_popular_user.py
echo "Finished scraping popular users from site"
echo

echo "====================================================================================="
echo "Scraping ratings from site. Even running asynchronously, this can take several hours."
echo "====================================================================================="
pipenv run python ./scraping/get_ratings.py
echo "Finished scraping ratings from site"
echo

echo "=============================="
echo "Scraping movie data from site."
echo "=============================="
pipenv run python ./scraping/get_movies.py
echo "Finished scraping movie data from site"
echo

echo "================================"
echo "Creating Training Data Sample..."
echo "================================"
pipenv run python ./model/create_training_data.py

echo "========="
echo "Finished!"
echo "========="
