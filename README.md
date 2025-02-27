# LETTERBOXD RECOMMENDER APP

## Configuração do Ambiente

1. Verifique a versão do Python:
   ```
   python --version
   ```
   Certifique-se de que é 3.11.0. Se não for, instale-a.

2. Crie um ambiente virtual:
   ```
   python -m venv venv
   ```

3. Ative o ambiente virtual:
   - No Windows:
     ```
     venv\Scripts\activate
     ```
   - No macOS e Linux:
     ```
     source venv/bin/activate
     ```

4. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```

   Caso ocorra erro:
   Se você receber um erro sobre "Microsoft Visual C++ 14.0 or greater is required", instale o "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/

## Executando o Projeto

1. Inicie o Redis:
   ```
   python worker.py
   ```

2. Inicie a API:
   ```
   uvicorn main:app --reload
   ```

## Populando o Banco de Dados

Execute os seguintes scripts nesta ordem:

1. `python scraping/get_popular_user.py`
2. `python scraping/get_ratings.py`
3. `python scraping/get_movies.py`

Nota: Pode ser necessário exportar a tabela de ratings do banco como CSV e adicioná-la à pasta 'data'.

## Treinamento do Modelo

Execute os seguintes scripts nesta ordem:

1. `python model/create_training_data.py`
2. `python model/build_model.py`
3. `python model/run_model.py`

## Parâmetros da URL

- username: Nome de usuário para quem o modelo está sendo construído
- training_data_size: Número de linhas para a amostra do conjunto de dados de treinamento
  - default: 200000
  - min: 100000
  - max: 800000
- popularity_threshold: Limite para filtrar filmes populares (opcional)
  - default: none
  - min: -1
  - max: 7
- num_items:
  - default: 30

## Endpoints da API

Após iniciar a API, use os seguintes endpoints para obter recomendações:

1. GET RECS (modifique os parâmetros de consulta conforme necessário):
   ```
   http://127.0.0.1:8000/get_recs?username={username}&training_data_size={size}&popularity_filter={filter}&data_opt_in={bool}
   ```

2. GET RESULTS (o Redis armazena os resultados por 30 segundos, use os IDs retornados na resposta do get_recs):
   ```
   http://127.0.0.1:8000/results?redis_build_model_job_id={model}&redis_get_user_data_job_id={user}
   ```

## Frontend

1. Acesse o diretório `/frontend`
2. Instale as dependências:
   ```
   npm install
   ```
3. Para iniciar o frontend, execute:
   ```
   npx next build
   npx next start
   ```
4. O frontend estará disponível em `http://localhost:3000`