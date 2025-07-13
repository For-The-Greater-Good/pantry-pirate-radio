# =============================================================================
# CONSOLIDATED DOCKERFILE FOR PANTRY PIRATE RADIO
# =============================================================================
# This replaces: Dockerfile.app, Dockerfile.worker, Dockerfile.reconciler,
# Dockerfile.recorder, Dockerfile.scraper, Dockerfile.test
# =============================================================================

# Base stage with common dependencies
FROM python:3.11-slim-bullseye as base

# Install system dependencies including Node.js for Claude CLI
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (v18 LTS)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry

# Configure Poetry
ENV POETRY_VIRTUALENVS_CREATE=false

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# =============================================================================
# PRODUCTION BASE - Install only production dependencies
# =============================================================================
FROM base as production-base

# Install production dependencies
RUN poetry install --without dev --no-interaction --no-ansi

# Copy application code
COPY app app/

# Set Python path
ENV PYTHONPATH=/app

# =============================================================================
# DEVELOPMENT/TEST BASE - Install all dependencies including dev
# =============================================================================
FROM base as development-base

# Install all dependencies including dev dependencies
RUN poetry install --no-interaction --no-ansi

# Copy all application code and config files
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# =============================================================================
# FASTAPI APPLICATION SERVICE
# =============================================================================
FROM production-base as app

# Expose the port the app runs on
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# WORKER SERVICES (LLM, Reconciler, Recorder)
# =============================================================================
FROM production-base as worker

# Copy startup script
COPY scripts/container_startup.sh /usr/local/bin/container_startup.sh
RUN chmod +x /usr/local/bin/container_startup.sh

# Use startup script as entrypoint with fallback to RQ worker
ENTRYPOINT ["/usr/local/bin/container_startup.sh"]
CMD ["rq", "worker", "llm"]

# =============================================================================
# RECORDER SERVICE
# =============================================================================
FROM production-base as recorder

# Create directories for outputs and archives
RUN mkdir -p /app/outputs /app/archives

# Start recorder worker
CMD ["rq", "worker", "recorder"]

# =============================================================================
# SCRAPER SERVICE
# =============================================================================
FROM production-base as scraper

# Start scraper service
CMD ["python", "-m", "app.scraper"]

# =============================================================================
# TEST SERVICE
# =============================================================================
FROM development-base as test

# Run tests
CMD ["poetry", "run", "pytest"]

# =============================================================================
# DATASETTE EXPORTER SERVICE
# =============================================================================
FROM production-base as datasette-exporter

# Install additional build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create data directory
RUN mkdir -p /data

# Set environment variables
ENV OUTPUT_DIR=/data
ENV EXPORT_INTERVAL=3600

# Set up entrypoint
ENTRYPOINT ["python", "-m", "app.datasette"]

# Default command
CMD ["schedule", "--verbose"]

# =============================================================================
# DEFAULT STAGE - FastAPI Application
# =============================================================================
FROM app as default
