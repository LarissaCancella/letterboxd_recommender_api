# LETTERBOXD RECOMMENDER APP

## Environment Setup

1. **Check Python version:**
   ```bash
   python --version
   ```
   Ensure it is version 3.11.0. If not, please install it.

2. **Create a virtual environment:**
   ```
   python -m venv venv
   ```

3. **Activate the virtual environment:**
   - On Windows:
     ```
     venv\Scripts\activate
     ```
   - On macOS and Linux:
     ```
     source venv/bin/activate
     ```

4. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

   **Troubleshooting:**
   If you encounter an error regarding "Microsoft Visual C++ 14.0 or greater is required", please install the Microsoft C++ Build Tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/

## Running the Project

1. **Start the Redis Worker:**
   ```
   python worker.py
   ```

2. **Start the API:**
   ```
   uvicorn main:app --reload
   ```

## Populating the Database

**Run the following scripts in this specific order:**

1. `python scraping/get_popular_user.py`
2. `python scraping/get_ratings.py`
3. `python scraping/get_movies.py`

Note: You may need to export the ratings table from the database as a CSV file and add it to the data folder.

## Model Training

**Run the following scripts in this specific order:**

1. `python model/create_training_data.py`
2. `python model/build_model.py`
3. `python model/run_model.py`

## URL Parameters

- **username:** The username for whom the model is being built.
- **training_data_size:** Number of rows for the training dataset sample.
  - default: 200000
  - min: 100000
  - max: 800000
- **popularity_threshold:** Threshold to filter popular movies (optional).
  - default: none
  - min: -1
  - max: 7
- **num_items:**
  - default: 30

## API Endpoints

After starting the API, use the following endpoints to get recommendations:

1. **GET RECS** (Modify query parameters as needed):
   ```
   http://127.0.0.1:8000/get_recs?username={username}&training_data_size={size}&popularity_filter={filter}&data_opt_in={bool}
   ```

2. **GET RESULTS** (Redis stores results for 30 seconds; use the IDs returned in the get_recs response):
   ```
   http://127.0.0.1:8000/results?redis_build_model_job_id={model}&redis_get_user_data_job_id={user}
   ```

## ⚠️ LEGAL NOTICE & PROPRIETARY RIGHTS

This is a unique, proprietary project protected by patent laws.

Access, use, reproduction, or distribution of this software by third parties is strictly prohibited. This code is for the exclusive use of the copyright holder and is not open source.
