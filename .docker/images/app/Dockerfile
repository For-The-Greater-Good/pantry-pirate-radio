# =============================================================================
# CONSOLIDATED DOCKERFILE FOR PANTRY PIRATE RADIO
# =============================================================================
# This replaces: Dockerfile.app, Dockerfile.worker, Dockerfile.reconciler,
# Dockerfile.recorder, Dockerfile.scraper, Dockerfile.test
#
# Two build paths share a common base-slim stage:
#   base-slim → production-slim → unified-slim  (worker, validator, etc.)
#   base-slim → base → production-base → unified (scraper, local dev)
# =============================================================================

# =============================================================================
# BASE-SLIM - Core system deps without browser/OCR packages
# =============================================================================
FROM python:3.11-slim-bullseye AS base-slim

# Install core system dependencies (no browser libs, no Node.js, no OCR)
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
    build-essential \
    libpq-dev \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && sh -c 'echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
    && apt-get update \
    && apt-get install -y postgresql-client-15 git-lfs \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Poetry (upgrade pip and wheel first to fix CVE-2025-8869 and CVE-2026-24049)
RUN pip install --upgrade pip>=26.0 wheel>=0.46.2 && pip install 'distlib<0.4.0' poetry

# Configure Poetry
ENV POETRY_VIRTUALENVS_CREATE=false

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# =============================================================================
# BASE - Full system deps (browser libs, Node.js, Claude CLI, OCR tools)
# =============================================================================
FROM base-slim AS base

# Install Playwright browser system dependencies, OCR tools, and Node.js
RUN apt-get update && apt-get install -y \
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
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (v18 LTS) - needed for Claude CLI in local dev
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI globally
RUN npm install -g @anthropic-ai/claude-code

# =============================================================================
# PRODUCTION-SLIM - Python deps without browser binaries
# =============================================================================
FROM base-slim AS production-slim

# Refresh pip to avoid attrs/pip vendor conflict during dependency resolution
RUN pip install --upgrade pip

# Install all Python dependencies (playwright pip package is tiny, ~1MB;
# we just skip installing the browser binary and system deps)
RUN poetry install --no-interaction --no-ansi

# Copy everything
COPY . .

# Create necessary directories
RUN mkdir -p /app/outputs /app/archives /data /app/data

# Set Python path
ENV PYTHONPATH=/app

# Make all scripts executable
RUN find scripts -name "*.sh" -exec chmod +x {} \;

# =============================================================================
# PRODUCTION BASE - Complete image with Playwright browsers
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
# UNIFIED-SLIM - Slim image for AWS non-scraper services
# =============================================================================
FROM production-slim AS unified-slim

# Make entrypoint script executable
RUN chmod +x /app/scripts/docker-entrypoint.sh

# Expose common ports (services can override in docker-compose)
EXPOSE 8000 8080 9181 5050 8001

# Use the unified entrypoint that selects service based on SERVICE_TYPE or args
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]

# Default to running the FastAPI app if no service specified
CMD ["app"]

# =============================================================================
# UNIFIED PRODUCTION IMAGE - Single image for all services (local dev + scraper)
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
