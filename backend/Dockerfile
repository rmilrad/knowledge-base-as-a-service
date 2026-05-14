FROM python:3.12-slim AS base

# Install system deps for PyPDF, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir .

# Copy application code
COPY . .

# Pre-download the embedding model at build time so it's baked into the image
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Create non-root user
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --ingroup app app && \
    chown -R app:app /app

EXPOSE 8000

# Run migrations then start server
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

USER app
CMD ["./entrypoint.sh"]
