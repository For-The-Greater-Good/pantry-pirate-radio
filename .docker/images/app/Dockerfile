# =============================================================================
# CONSOLIDATED DOCKERFILE FOR PANTRY PIRATE RADIO
# =============================================================================
# This replaces: Dockerfile.app, Dockerfile.worker, Dockerfile.reconciler,
# Dockerfile.recorder, Dockerfile.scraper, Dockerfile.test
# =============================================================================

# Base stage with common dependencies
FROM python:3.11-slim-bullseye AS base

# Install system dependencies including Node.js for Claude CLI and Playwright
# First add PostgreSQL 15 repository to get matching client version
RUN apt-get update && apt-get install -y \
    curl \
    git \
    git-lfs \
    jq \
    lsb-release \
    gnupg \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    build-essential \
    libpq-dev \
    && sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt-get update \
    && apt-get install -y postgresql-client-15 git-lfs \
    && git lfs install \
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
# PRODUCTION BASE - Complete image with everything
# =============================================================================
FROM base AS production-base

# Install all dependencies (including dev for full functionality)
RUN poetry install --no-interaction --no-ansi

# Install Playwright browsers after poetry install
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy everything
COPY . .

# Create necessary directories
RUN mkdir -p /app/outputs /app/archives /data /app/data

# Set Python path
ENV PYTHONPATH=/app

# Make all scripts executable
RUN find scripts -name "*.sh" -exec chmod +x {} \;

# Note: development-base is now same as production-base since we include everything

# =============================================================================
# FASTAPI APPLICATION SERVICE
# =============================================================================
FROM production-base AS app

# Expose the port the app runs on
EXPOSE 8000

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# LLM WORKER SERVICE (with Claude authentication and multi-worker support)
# =============================================================================
FROM production-base AS worker

# Use startup script as entrypoint with fallback to RQ worker
ENTRYPOINT ["/app/scripts/container_startup.sh"]
CMD ["rq", "worker", "llm"]

# =============================================================================
# SIMPLE RQ WORKER SERVICE (for other queues without Claude setup)
# =============================================================================
FROM production-base AS simple-worker

# Start RQ worker directly without startup scripts
CMD ["rq", "worker"]

# =============================================================================
# RECORDER SERVICE
# =============================================================================
FROM production-base AS recorder

# Start recorder worker
CMD ["rq", "worker", "recorder"]

# =============================================================================
# SCRAPER SERVICE
# =============================================================================
FROM production-base AS scraper

# Start scraper service
CMD ["python", "-m", "app.scraper"]

# =============================================================================
# TEST SERVICE
# =============================================================================
FROM production-base AS test

# Run tests
CMD ["poetry", "run", "pytest"]

# =============================================================================
# UNIFIED PRODUCTION IMAGE - Single image for all services
# =============================================================================
FROM production-base AS unified

# Make entrypoint script executable
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Expose common ports (services can override in docker-compose)
EXPOSE 8000 8080 9181 5050 8001

# Use the unified entrypoint that selects service based on SERVICE_TYPE or args
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# Default to running the FastAPI app if no service specified
CMD ["app"]

# =============================================================================
# DEFAULT STAGE - FastAPI Application (kept for backward compatibility)
# =============================================================================
FROM app AS default
