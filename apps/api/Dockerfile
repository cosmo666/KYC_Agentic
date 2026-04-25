# apps/api/Dockerfile
FROM python:3.11-slim

# System deps for DeepFace (opencv, Pillow) and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /app

# Copy manifest first for layer caching. Install dev deps too so we can run
# tests/migrations inside the container during development.
COPY pyproject.toml ./
RUN uv sync

COPY app ./app
COPY tests ./tests
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# Upload dir (mounted as a volume in compose)
RUN mkdir -p /data/uploads

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
