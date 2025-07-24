#!/bin/bash
# Multi-worker startup script for RQ

set -e

# Get worker count from environment, default to 1
WORKER_COUNT=${WORKER_COUNT:-1}
QUEUE_NAME=${QUEUE_NAME:-llm}

echo "🚀 Starting $WORKER_COUNT RQ workers for queue: $QUEUE_NAME"

# Clean up any stale worker registrations (optional, only if Redis is available)
if command -v redis-cli &> /dev/null && redis-cli -u "${REDIS_URL:-redis://cache:6379}" ping &> /dev/null; then
    echo "🧹 Cleaning up stale worker registrations..."
    # Remove dead workers from the registry
    redis-cli -u "${REDIS_URL:-redis://cache:6379}" eval "
        local keys = redis.call('keys', 'rq:worker:*')
        for i=1,#keys do
            local key = keys[i]
            local heartbeat = redis.call('hget', key, 'last_heartbeat')
            if heartbeat and tonumber(heartbeat) < (redis.call('time')[1] - 60) then
                redis.call('del', key)
            end
        end
        return #keys
    " 0 &> /dev/null || echo "⚠️  Redis cleanup failed (continuing anyway)"
fi

# Store worker PIDs for proper cleanup
WORKER_PIDS=()

# Function to handle shutdown
cleanup() {
    echo "🛑 Shutting down workers..."
    # Kill specific worker processes
    for pid in "${WORKER_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait
    echo "✅ All workers stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Generate unique worker names with container ID or timestamp
CONTAINER_ID=${HOSTNAME:-$(date +%s)}

# Start workers in background
for i in $(seq 1 $WORKER_COUNT); do
    WORKER_NAME="worker-${CONTAINER_ID}-$i"
    echo "🔧 Starting worker $i/$WORKER_COUNT (name: $WORKER_NAME)..."

    # Check if worker name already exists and clean it up if stale
    if command -v redis-cli &> /dev/null; then
        redis-cli -u "${REDIS_URL:-redis://cache:6379}" del "rq:worker:$WORKER_NAME" &> /dev/null || true
    fi

    # Use explicit command to avoid any configuration conflicts
    echo "   Command: /usr/local/bin/python -m rq.cli worker $QUEUE_NAME --name $WORKER_NAME"
    /usr/local/bin/python -m rq.cli worker "$QUEUE_NAME" --name "$WORKER_NAME" 2>&1 &
    WORKER_PID=$!
    WORKER_PIDS+=($WORKER_PID)
    echo "   Started with PID: $WORKER_PID"

    # Small delay to avoid race conditions
    sleep 0.1
done

echo "✅ All $WORKER_COUNT workers started"
echo ""

# Show worker PIDs
echo "Worker PIDs:"
printf '%s\n' "${WORKER_PIDS[@]}"

# Wait for all background jobs
wait