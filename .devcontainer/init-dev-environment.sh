#!/bin/bash
set -e

# Source shared functions
source "$(dirname "$0")/shared-env-setup.sh"

echo "🚀 Initializing Pantry Pirate Radio Dev Environment..."

# Ensure we're in the workspace
cd /workspace

# Validate environment first
if ! validate_environment; then
    echo "⚠️  Environment validation failed - some features may not work"
fi

# Wait for Docker to be ready
if ! wait_for_docker 30 2; then
    echo "⚠️  Continuing without Docker - you'll need to start it manually"
fi

# Check if .env exists, if not create it
if [ ! -f .env ]; then
    echo "📝 No .env file found. Creating default configuration..."
    env_type="development"
    [ -n "$CODESPACES" ] && env_type="codespaces"
    create_default_env ".env" "$env_type"
fi

# Note: We no longer copy .env to .docker/compose/ as we've standardized on root .env

# Codespaces-specific configuration
if [ -n "$CODESPACES" ]; then
    echo "🔧 Detected Codespaces environment"
    # BuildKit settings are now in the .env file
fi

# Configure git
setup_git_config

# Install pre-commit hooks
if [ -f .pre-commit-config.yaml ]; then
    echo "🪝 Installing pre-commit hooks..."
    pre-commit install || echo "⚠️  Pre-commit hooks installation failed (non-critical)"
fi

echo "✨ Dev environment initialization complete!"
echo ""

# Show helpful startup message
show_startup_message