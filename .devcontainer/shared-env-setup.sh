#!/bin/bash
# Shared environment setup functions for DevContainer initialization

# Create default .env file with consistent content
create_default_env() {
    local env_file="${1:-.env}"
    local env_type="${2:-development}"  # development, codespaces, or test
    
    cat > "$env_file" << 'EOF'
# Database Configuration
DATABASE_URL=postgresql://postgres:devcontainer@db:5432/pantry_pirate_radio
TEST_DATABASE_URL=postgresql://postgres:devcontainer@db:5432/test_pantry_pirate_radio

# Redis Configuration
REDIS_URL=redis://cache:6379/0
TEST_REDIS_URL=redis://cache:6379/1

# Content Store Configuration
CONTENT_STORE_PATH=/workspace/content_store

# LLM Provider Configuration
LLM_PROVIDER=claude
# IMPORTANT: Replace these placeholder values with real API keys
# For Codespaces, use GitHub Secrets: https://docs.github.com/en/codespaces/managing-your-codespaces/managing-secrets-for-your-codespaces
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# HAARRRvest Publisher Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
# IMPORTANT: Use a GitHub Personal Access Token with repo scope
DATA_REPO_TOKEN=github_pat_placeholder
PUBLISHER_PUSH_ENABLED=false

# Postgres Configuration (for Docker Compose)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=devcontainer
POSTGRES_DB=pantry_pirate_radio

# Development Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
REDIS_TTL_SECONDS=2592000
EOF

    # Add environment-specific overrides
    if [ "$env_type" = "codespaces" ]; then
        cat >> "$env_file" << 'EOF'

# Codespaces-specific settings
# BuildKit disabled for compatibility
DOCKER_BUILDKIT=0
COMPOSE_DOCKER_CLI_BUILD=0
EOF
    fi
    
    echo "✅ Created default .env file for $env_type environment"
}

# Wait for Docker with improved error handling
wait_for_docker() {
    local max_attempts="${1:-30}"
    local wait_seconds="${2:-2}"
    local attempt=0
    
    echo "🐳 Waiting for Docker daemon..."
    
    while [ $attempt -lt $max_attempts ]; do
        if timeout 5 docker info >/dev/null 2>&1; then
            echo "✅ Docker daemon is ready!"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo "  Attempt $attempt/$max_attempts - Docker not ready yet..."
        sleep $wait_seconds
    done
    
    echo "❌ Docker daemon failed to start after $((max_attempts * wait_seconds)) seconds"
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check if Docker Desktop is running (if using Docker Desktop)"
    echo "2. Try: sudo systemctl start docker (if using system Docker)"
    echo "3. Check Docker logs: docker version"
    echo ""
    return 1
}

# Validate required tools
validate_environment() {
    local errors=0
    
    echo "🔍 Validating environment..."
    
    # Check for required commands
    for cmd in git docker; do
        if ! command -v $cmd >/dev/null 2>&1; then
            echo "❌ Required command not found: $cmd"
            errors=$((errors + 1))
        fi
    done
    
    # Check workspace
    if [ ! -d "/workspace" ]; then
        echo "❌ Workspace directory not found at /workspace"
        errors=$((errors + 1))
    fi
    
    # Check if bouy exists
    if [ -f "/workspace/bouy" ]; then
        chmod +x /workspace/bouy /workspace/bouy-api 2>/dev/null || true
    else
        echo "⚠️  bouy not found - clone may not be complete"
    fi
    
    if [ $errors -gt 0 ]; then
        echo "❌ Environment validation failed with $errors error(s)"
        return 1
    fi
    
    echo "✅ Environment validation passed"
    return 0
}

# Setup git configuration
setup_git_config() {
    if [ -f "$HOME/.gitconfig" ]; then
        echo "✅ Git configuration found"
    else
        echo "📋 Setting up basic git configuration..."
        git config --global user.email "${GIT_USER_EMAIL:-dev@devcontainer.local}"
        git config --global user.name "${GIT_USER_NAME:-Dev Container User}"
        git config --global init.defaultBranch main
        echo "✅ Git configuration created"
    fi
}

# Display helpful startup message
show_startup_message() {
    cat << 'EOF'

🚢 Pantry Pirate Radio DevContainer Ready!

Quick Start Commands:
  ./bouy up --with-init    # First time - initializes database
  ./bouy up                # Subsequent runs
  ./bouy test              # Run all tests
  ./bouy --help            # See all commands

Service Management:
  ./bouy ps                # Check service status
  ./bouy logs app -f       # Follow app logs
  ./bouy shell app         # Shell into app container
  ./bouy down              # Stop all services

Development:
  ./bouy test --pytest     # Run tests only
  ./bouy test --mypy       # Type checking only
  ./bouy scraper --list    # List available scrapers

EOF

    # Add environment-specific notes
    if [ -n "$CODESPACES" ]; then
        cat << 'EOF'
📍 Codespaces Notes:
  - API keys should be set via Codespaces Secrets
  - Port 8000 is auto-forwarded for the API
  - Use the Ports tab to access other services

EOF
    fi
}