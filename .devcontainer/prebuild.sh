#!/bin/bash
set -e

# Source shared functions
source "$(dirname "$0")/shared-env-setup.sh"

echo "🏗️ Running Codespaces prebuild tasks..."

# Ensure we're in the workspace
cd /workspace

# Validate environment
validate_environment || true

# Set up environment for Codespaces
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0

# Wait for Docker to be ready with shorter timeout for prebuild
if ! wait_for_docker 30 2; then
    echo "⚠️ Docker daemon not ready for prebuild - skipping image build"
    exit 0
fi

# Create default .env file for prebuild
if [ ! -f .env ]; then
    echo "📝 Creating default .env for prebuild..."
    create_default_env ".env" "codespaces"
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