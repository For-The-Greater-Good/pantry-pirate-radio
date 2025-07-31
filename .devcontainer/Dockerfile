# Use Ubuntu as base for maximum compatibility
FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Basic tools
    curl \
    wget \
    git \
    sudo \
    ca-certificates \
    gnupg \
    lsb-release \
    build-essential \
    software-properties-common \
    # Python and development tools
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    # PostgreSQL client tools
    postgresql-client \
    # Redis tools
    redis-tools \
    # Editor and utilities
    vim \
    nano \
    htop \
    jq \
    # Required for some Python packages
    libpq-dev \
    libssl-dev \
    libffi-dev \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Note: Docker will be installed by the Docker-in-Docker dev container feature

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

# Install Poetry system-wide
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - && \
    ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry && \
    chmod -R 755 /opt/poetry

# Install pre-commit
RUN pip3 install --no-cache-dir pre-commit

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

# Create workspace directory
RUN mkdir -p /workspace && chown -R $USERNAME:$USERNAME /workspace

# Install Node.js via NVM for the vscode user
USER $USERNAME
ENV NVM_DIR="/home/vscode/.nvm"
RUN mkdir -p "$NVM_DIR" \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install 24 \
    && nvm use 24 \
    && npm install -g @anthropic-ai/claude-code

# Switch back to root for final setup
USER root

# Add NVM to PATH for all users
RUN echo 'export NVM_DIR="/home/vscode/.nvm"' >> /etc/bash.bashrc \
    && echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> /etc/bash.bashrc \
    && echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> /etc/bash.bashrc

# Copy initialization script
COPY .devcontainer/init-dev-environment.sh /usr/local/bin/init-dev-environment.sh
RUN chmod +x /usr/local/bin/init-dev-environment.sh

# Switch to non-root user
USER $USERNAME
WORKDIR /workspace

# Set up Poetry for user
RUN poetry config virtualenvs.create true && \
    poetry config virtualenvs.in-project false && \
    poetry config virtualenvs.path /home/$USERNAME/.virtualenvs

# Environment variables
ENV PATH="/home/$USERNAME/.local/bin:$PATH"
ENV DOCKER_BUILDKIT=1
ENV COMPOSE_DOCKER_CLI_BUILD=1
ENV POETRY_VIRTUALENVS_PATH=/home/$USERNAME/.virtualenvs
ENV POETRY_CACHE_DIR=/home/$USERNAME/.cache/poetry

# Default command
CMD ["/bin/bash"]
