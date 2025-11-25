# 1. Lightweight base image
FROM python:3.10-slim

# 2. Settings to prevent .pyc files and buffering (ensures logs are printed immediately)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Install system dependencies (required for ML libraries like Pandas/NumPy)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Working directory
WORKDIR /app

# 5. Install project dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Ensure web servers are installed even if missing from requirements
RUN pip install gunicorn uvicorn

# 6. Copy source code
COPY . .

# 7. Expose default port (documentation only; Portainer manages this)
EXPOSE 5000

# The default CMD will be overwritten in Portainer, so we provide a default here
CMD ["python", "main.py"]