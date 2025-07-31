#!/bin/bash
set -e

echo "🏗️ Running Codespaces prebuild tasks..."

# Ensure we're in the workspace
cd /workspace

# Make bouy executable
chmod +x bouy bouy-api

# Set up environment for Codespaces
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

# Wait for Docker to be ready
echo "Waiting for Docker daemon..."
timeout=60
while ! docker ps >/dev/null 2>&1 && [ $timeout -gt 0 ]; do
    echo "Waiting for Docker daemon to start... ($timeout seconds remaining)"
    sleep 2
    ((timeout-=2))
done

if [ $timeout -eq 0 ]; then
    echo "⚠️ Docker daemon not ready for prebuild - skipping image build"
    exit 0
fi

echo "✅ Docker daemon is ready!"

# Create default .env file for prebuild
if [ ! -f .env ]; then
    echo "📝 Creating default .env for prebuild..."
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
fi

# Copy .env to compose directory
if [ ! -f .docker/compose/.env ]; then
    cp .env .docker/compose/.env
fi

# Build Docker images
echo "🐳 Building Docker images for prebuild..."
if ./bouy build; then
    echo "✅ Docker images prebuilt successfully!"
    
    # Pull base images to cache them
    echo "📦 Pulling base images..."
    docker pull postgis/postgis:15-3.3 || true
    docker pull redis:7-alpine || true
    docker pull prodrigestivill/postgres-backup-local:15 || true
    
    echo "✅ Prebuild completed successfully!"
else
    echo "⚠️ Docker image prebuild failed - images will be built on first use"
fi