#!/bin/bash
set -e

echo "🚀 Initializing Pantry Pirate Radio Dev Environment..."

# Ensure we're in the workspace
cd /workspace

# Wait for Docker to be ready (Docker-in-Docker feature starts it automatically)
echo "Waiting for Docker daemon..."
timeout=60
while ! docker ps >/dev/null 2>&1 && [ $timeout -gt 0 ]; do
    echo "Waiting for Docker daemon to start... ($timeout seconds remaining)"
    sleep 2
    ((timeout-=2))
done
if [ $timeout -eq 0 ]; then
    echo "❌ Docker daemon failed to start"
    echo "Trying to diagnose the issue..."
    docker version || true
    exit 1
fi
echo "✅ Docker daemon is ready!"

# Make bouy executable
chmod +x bouy bouy-api

# Check if .env exists, if not run setup
if [ ! -f .env ]; then
    echo "📝 No .env file found. Running bouy setup..."
    # Create a basic .env file for dev container
    cat > .env << 'EOF'
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
ANTHROPIC_API_KEY=placeholder_key

# HAARRRvest Publisher Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=placeholder_token
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
    echo "✅ Created default .env file for dev container"
fi

# Copy .env to compose directory (compose files expect it there)
if [ -f .env ] && [ ! -f .docker/compose/.env ]; then
    echo "📋 Copying .env to .docker/compose/ directory..."
    cp .env .docker/compose/.env
    echo "✅ Copied .env to compose directory"
fi

# Codespaces-specific workarounds
if [ -n "$CODESPACES" ]; then
    echo "🔧 Detected Codespaces environment - applying workarounds..."
    # Disable BuildKit to avoid multi-stage build issues in Codespaces
    echo "export DOCKER_BUILDKIT=0" >> ~/.bashrc
    echo "export COMPOSE_DOCKER_CLI_BUILD=0" >> ~/.bashrc
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0
    echo "✅ Disabled Docker BuildKit for Codespaces compatibility"
fi

# Display startup instructions instead of auto-starting
echo ""
echo "🚢 Services are ready to launch!"
echo ""
echo "To start the services, run one of these commands:"
echo ""
echo "  ./bouy up --with-init    # Start with database initialization (first time)"
echo "  ./bouy up                # Start services (subsequent runs)"
echo ""
echo "This gives you control over when to start the services and avoids"
echo "potential Docker-in-Docker timing issues during container initialization."
echo ""

# Configure git if needed
if [ -f /home/vscode/.gitconfig ]; then
    echo "📋 Git configuration found"
else
    echo "📋 Setting up basic git configuration..."
    git config --global user.email "dev@devcontainer.local"
    git config --global user.name "Dev Container User"
fi

# Install pre-commit hooks
if [ -f .pre-commit-config.yaml ]; then
    echo "🪝 Installing pre-commit hooks..."
    pre-commit install || echo "⚠️  Pre-commit hooks installation failed (non-critical)"
fi

echo "✨ Dev environment initialization complete!"
echo ""
echo "🎯 Next steps:"
echo "  1. Start the services:     ./bouy up --with-init"
echo "  2. View service status:    ./bouy ps"
echo "  3. Check logs if needed:   ./bouy logs app"
echo ""
echo "📚 Useful commands:"
echo "  ./bouy test        - Run all tests"
echo "  ./bouy shell app   - Open shell in app container"
echo "  ./bouy down        - Stop all services"
echo "  ./bouy --help      - See all available commands"
echo ""
echo "💡 Tip: If you encounter the '/.docker' error, try:"
echo "  - Running 'docker system prune -a' and rebuilding"
echo "  - Or use './bouy build' before './bouy up'"