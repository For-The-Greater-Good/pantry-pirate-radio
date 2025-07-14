FROM mcr.microsoft.com/devcontainers/python:3.11-bullseye as app

# Install system dependencies including GitHub CLI
RUN apt-get update && apt-get install -y \
    postgresql-client \
    sudo \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    && cat $out | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && mkdir -p -m 755 /etc/apt/sources.list.d \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Add sudo access for vscode user
RUN echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/vscode

# Create required directories
RUN mkdir -p /opt/poetry /opt/poetry-venv /opt/.cache /workspace/.virtualenvs /workspace/.cache/poetry

# Set environment variables for Poetry
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv
ENV POETRY_CACHE_DIR=/opt/.cache

# Install poetry separated from system interpreter
RUN python3 -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry

# Add poetry to PATH
ENV PATH="${PATH}:${POETRY_VENV}/bin"

# Install pre-commit
RUN $POETRY_VENV/bin/pip install pre-commit

# Install Node.js via NVM
ENV NVM_DIR="/home/vscode/.nvm"
RUN mkdir -p "$NVM_DIR" \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install 24 \
    && nvm use 24 \
    && npm install -g @anthropic-ai/claude-code

# Add NVM to PATH for all users
RUN echo 'export NVM_DIR="/home/vscode/.nvm"' >> /etc/bash.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> /etc/bash.bashrc \
    && echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> /etc/bash.bashrc

# Create and set permissions for vscode directories
RUN mkdir -p /home/vscode/.vscode-server \
    && chown -R vscode:vscode /workspace /opt/poetry /opt/poetry-venv /opt/.cache /home/vscode/.vscode-server /home/vscode/.nvm

USER vscode
WORKDIR /workspace

# Add the configuration script to .bashrc and NVM setup
RUN echo '[ -f /usr/local/bin/configure-poetry.sh ] && source /usr/local/bin/configure-poetry.sh' >> ~/.bashrc \
    && echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> ~/.bashrc \
    && echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> ~/.bashrc
