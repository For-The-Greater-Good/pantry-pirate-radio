# =============================================================================
# SUBMARINE IMAGE — crawl4ai + Chromium on slim Python base
# =============================================================================
# Dedicated image for the submarine web crawler. Built on the same base-slim
# as the unified image but adds only what submarine needs:
#   - Chromium browser libs (subset of the full image's browser deps)
#   - crawl4ai (web crawler that produces LLM-ready markdown)
#   - Playwright Chromium browser binary
#
# Size target: ~1.5-2GB (vs ~10GB full unified image)
# =============================================================================

FROM python:3.11-slim-bullseye

# Install core system deps (same as base-slim in the main Dockerfile)
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
    && apt-get install -y postgresql-client-15 \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium browser system dependencies (Playwright requirement)
# This is the subset of browser libs needed for headless Chromium — no
# Node.js, no Claude CLI, no tesseract/OCR (those are in the full image only)
RUN apt-get update && apt-get install -y \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pip, wheel, poetry
RUN pip install --upgrade pip>=26.0 wheel>=0.46.2 && pip install 'distlib<0.4.0' poetry

ENV POETRY_VIRTUALENVS_CREATE=false

# Copy dependency files and install Python deps
COPY pyproject.toml poetry.lock ./
RUN pip install --upgrade pip && poetry install --no-interaction --no-ansi

# Install crawl4ai + Playwright Chromium browser binary
RUN pip install crawl4ai && playwright install chromium

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/outputs /app/archives /data /app/data

# Entrypoint
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]

# Default: run the submarine Fargate worker
CMD ["submarine"]
