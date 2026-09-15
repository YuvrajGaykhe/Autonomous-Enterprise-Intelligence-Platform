# AI CEO — Layer 1 API Dockerfile
# Builds the FastAPI application container.

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by psycopg2-binary.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first for better layer caching.
COPY pyproject.toml ./

# Install runtime dependencies only (no dev extras in the container).
RUN pip install --no-cache-dir .

# Copy application source and migration configuration.
COPY app/ ./app/
# Runtime configuration resolved relative to the project root (/app/config):
# connectors, normalization mappings (D1), and the quality gate (D2).
COPY config/ ./config/
# Committed demo dataset read by the csv_demo connector (data_directory: data/demo,
# resolved against /app). The mock-source image bakes in the same files, so rebuild
# both images after regenerating data/demo. Test fixtures are deliberately excluded.
COPY data/demo/ ./data/demo/
COPY alembic.ini ./
COPY migrations/ ./migrations/

# Expose the API port (matches APP_PORT in .env.example).
EXPOSE 8000

# Start the FastAPI application via Uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
