#!/bin/bash
set -e

# Docker entrypoint script for unified production image
# Selects the appropriate service to run based on SERVICE_TYPE env var or first argument

SERVICE="${SERVICE_TYPE:-$1}"

echo "DEBUG: Received SERVICE='$SERVICE'"
echo "DEBUG: All args: $@"

case "$SERVICE" in
    app|api|fastapi)
        echo "Starting FastAPI application..."
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    
    worker|llm-worker)
        echo "Starting LLM worker (LLM_PROVIDER=$LLM_PROVIDER)..."
        # Always use container_startup.sh which handles multi-worker setup
        exec /app/scripts/container_startup.sh rq worker llm
        ;;
    
    simple-worker)
        # For non-LLM workers that don't need Claude setup
        QUEUE="${QUEUE_NAME:-${2:-default}}"
        echo "Starting simple RQ worker for queue: $QUEUE"
        exec rq worker "$QUEUE"
        ;;
    
    recorder)
        echo "Starting recorder worker..."
        if [ "$QUEUE_BACKEND" = "sqs" ]; then
            exec python -m app.recorder.fargate_worker
        else
            exec rq worker recorder
        fi
        ;;

    reconciler)
        echo "Starting reconciler worker..."
        if [ "$QUEUE_BACKEND" = "sqs" ]; then
            exec python -m app.reconciler.fargate_worker
        else
            exec rq worker reconciler
        fi
        ;;

    validator)
        echo "Starting validator worker..."
        if [ "$QUEUE_BACKEND" = "sqs" ]; then
            exec python -m app.validator.fargate_worker
        else
            exec rq worker validator
        fi
        ;;

    submarine)
        echo "Starting submarine worker..."
        if [ "$QUEUE_BACKEND" = "sqs" ]; then
            exec python -m app.submarine.fargate_worker
        else
            exec rq worker submarine
        fi
        ;;
    
    scraper)
        echo "Starting scraper service..."
        if [ -n "$2" ]; then
            # If additional arguments provided, pass them to scraper
            shift
            exec python -m app.scraper "$@"
        elif [ -n "$SCRAPER_NAME" ] && [ "$SCRAPER_NAME" != "placeholder" ]; then
            # SCRAPER_NAME env var set by Step Functions container override
            echo "Running scraper from env: $SCRAPER_NAME"
            exec python -m app.scraper "$SCRAPER_NAME"
        else
            # Default scraper behavior
            exec tail -f /dev/null  # Keep container running for manual scraper runs
        fi
        ;;
    
    haarrrvest-publisher|publisher)
        echo "Starting HAARRRvest publisher service..."
        exec python -m app.haarrrvest_publisher.service
        ;;
    
    content-store-dashboard|dashboard)
        echo "Starting content store dashboard..."
        exec python -m app.content_store.dashboard
        ;;
    
    rq-dashboard)
        echo "Starting RQ dashboard..."
        REDIS_URL="${REDIS_URL:-redis://cache:6379}"
        exec rq-dashboard -u "$REDIS_URL"
        ;;
    
    db-init|init)
        echo "Starting database initialization..."
        exec /app/scripts/init-database.sh
        ;;
    
    test)
        echo "Running tests..."
        exec poetry run pytest "$@"
        ;;
    
    shell|bash)
        echo "Starting interactive shell..."
        exec /bin/bash
        ;;
    
    *)
        # If no recognized service, execute the command directly
        echo "Executing command: $@"
        exec "$@"
        ;;
esac
