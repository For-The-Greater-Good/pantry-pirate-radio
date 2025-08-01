# DevContainer Dockerfile for Pantry Pirate Radio
# Optimized for both VSCode DevContainers and GitHub Codespaces

FROM mcr.microsoft.com/devcontainers/python:3.11-bullseye

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install essential system dependencies only
RUN apt-get update && apt-get install -y \
    # PostgreSQL client for database interaction
    postgresql-client \
    # Redis tools for cache debugging
    redis-tools \
    # GitHub CLI for PR operations
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (already has Python 3.11)
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Install pre-commit
RUN pip3 install --no-cache-dir pre-commit

# Install Node.js via the official NodeSource repository for claude-code
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

# Create workspace directory
RUN mkdir -p /workspace

# Copy initialization scripts
COPY .devcontainer/init-dev-environment.sh /usr/local/bin/init-dev-environment.sh
COPY .devcontainer/shared-env-setup.sh /usr/local/bin/shared-env-setup.sh
RUN chmod +x /usr/local/bin/init-dev-environment.sh /usr/local/bin/shared-env-setup.sh

# Set up Poetry for the default user
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project false \
    && poetry config virtualenvs.path /home/vscode/.virtualenvs 2>/dev/null || true

# Environment variables
ENV DOCKER_BUILDKIT=1
ENV COMPOSE_DOCKER_CLI_BUILD=1

WORKDIR /workspace

# Default command
CMD ["/bin/bash"]