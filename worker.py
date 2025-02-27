from dotenv import load_dotenv
load_dotenv()  # Isso carrega as variáveis do arquivo .env

import os
import redis
from rq import Worker, Queue

# Filas que o worker vai escutar
listen = ['high', 'default', 'low']

# Lê as variáveis de ambiente
redis_host = os.environ.get('REDIS_HOST')
redis_port = os.environ.get('REDIS_PORT')
redis_username = os.environ.get('REDIS_USERNAME')
redis_password = os.environ.get('REDIS_PASSWORD')

# Verifica se todas as variáveis necessárias estão presentes
if not all([redis_host, redis_port, redis_username, redis_password]):
    raise ValueError("Todas as variáveis de ambiente REDIS_* devem estar definidas")

# Converte a porta para inteiro
try:
    redis_port = int(redis_port)
except ValueError:
    raise ValueError(f"REDIS_PORT deve ser um número inteiro, recebido: {redis_port}")

# Conecta ao Redis
conn = redis.Redis(
    host=redis_host,
    port=redis_port,
    username=redis_username,
    password=redis_password,
)

if __name__ == '__main__':
    print("Iniciando o worker RQ...")
    print(f"Conectando ao Redis em {redis_host}:{redis_port}")
    queues = [Queue(name, connection=conn) for name in listen]
    worker = Worker(queues, connection=conn)
    worker.work()