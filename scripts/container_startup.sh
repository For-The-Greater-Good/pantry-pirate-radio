#!/bin/bash
# Container startup script for worker authentication setup

set -e

# Only show Claude-specific messages if using Claude provider
if [[ "$LLM_PROVIDER" == "claude" || "$LLM_PROVIDER" == "anthropic" ]]; then
    echo "🚀 Starting Claude-enabled worker container..."
    echo ""

    # Check if Claude CLI is available
    if ! command -v claude &> /dev/null; then
        echo "❌ Claude CLI not found. Please check Docker image build."
        exit 1
    fi

    echo "✅ Claude CLI found at: $(which claude)"
    echo ""

    # Check Claude authentication status
    echo "🔍 Checking Claude authentication status..."
    set +e  # Don't exit on error for auth check
    python -m app.claude_auth_manager status
    auth_status=$?
    set -e  # Re-enable exit on error

    if [ $auth_status -eq 0 ]; then
        echo ""
        echo "✅ Claude is authenticated and ready!"
        echo "🎯 Worker will process jobs normally."
    else
        echo ""
        echo "⚠️  Claude authentication required!"
        echo ""
        echo "📋 To authenticate Claude with your account:"
        echo "   1. In another terminal, run:"
        echo "      docker compose exec worker python -m app.claude_auth_manager setup"
        echo ""
        echo "   2. Or for interactive shell:"
        echo "      docker compose exec worker bash"
        echo "      python -m app.claude_auth_manager setup"
        echo ""
        echo "🔄 Jobs will be safely queued and retried every 5 minutes"
        echo "   until authentication is complete."
    fi

    echo ""
    echo "🎛️  Available commands in container:"
    echo "   python -m app.claude_auth_manager status    # Check auth status"
    echo "   python -m app.claude_auth_manager setup     # Run auth setup"
    echo "   python -m app.claude_auth_manager test      # Test Claude request"
    echo "   python -m app.claude_auth_manager config    # Show config files"
    echo ""

    # Optionally start health server in background
    if [ "$CLAUDE_HEALTH_SERVER" = "true" ]; then
        echo "🏥 Starting Claude health server on port 8080..."
        python -m app.claude_health_server 8080 &
        echo ""
    fi
else
    echo "🚀 Starting worker container (LLM_PROVIDER=$LLM_PROVIDER)..."
    echo ""
fi

# Validate and handle worker count
WORKER_COUNT=${WORKER_COUNT:-1}

# Validate WORKER_COUNT is a positive integer between 1 and 20
if [[ "$WORKER_COUNT" =~ ^[0-9]+$ ]] && [ "$WORKER_COUNT" -ge 1 ] && [ "$WORKER_COUNT" -le 20 ]; then
    if [ "$WORKER_COUNT" -gt 1 ]; then
        echo "🔧 Starting $WORKER_COUNT RQ workers..."
        exec /app/scripts/multi_worker.sh
    else
        # Start single worker (default behavior)
        echo "🔧 Starting single RQ worker..."
        # Check if this is the llm queue worker AND we're using Claude
        if [[ "$*" == *"llm"* ]] && [[ "$LLM_PROVIDER" == "claude" || "$LLM_PROVIDER" == "anthropic" ]]; then
            echo "   Using Claude-aware worker for LLM queue"
            exec /usr/local/bin/python /app/scripts/claude_worker.py llm
        else
            exec "$@"
        fi
    fi
else
    echo "⚠️ Invalid WORKER_COUNT: '$WORKER_COUNT'. Must be an integer between 1-20."
    echo "   Defaulting to single worker mode."
    echo "🔧 Starting single RQ worker..."
    exec "$@"
fi