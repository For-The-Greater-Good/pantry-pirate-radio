#!/bin/bash
set -e

# Docker management convenience script
COMPOSE_FILES="-f .docker/compose/base.yml"
COMPOSE_CMD="docker compose"

# Function to show usage
usage() {
    echo "Usage: ./docker.sh COMMAND [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  up [SERVICE]        Start services (dev mode by default)"
    echo "  down                Stop all services"
    echo "  build [SERVICE]     Build services"
    echo "  logs [SERVICE]      View logs (follows by default)"
    echo "  shell SERVICE       Open shell in service container"
    echo "  exec SERVICE CMD    Execute command in service container"
    echo "  ps                  List running services"
    echo "  test                Run tests in Docker"
    echo "  clean               Stop services and remove volumes"
    echo ""
    echo "Environment modes (use with 'up'):"
    echo "  --dev               Development mode (default)"
    echo "  --prod              Production mode"
    echo "  --test              Test mode"
    echo "  --with-init         Include database initialization"
    echo ""
    echo "Examples:"
    echo "  ./docker.sh up                    # Start dev environment"
    echo "  ./docker.sh up --prod             # Start production environment"
    echo "  ./docker.sh up worker --dev       # Start only worker in dev mode"
    echo "  ./docker.sh logs app              # View app logs"
    echo "  ./docker.sh shell app             # Open shell in app container"
    echo "  ./docker.sh test                  # Run tests"
}

# Parse environment mode
parse_mode() {
    local mode="dev"
    for arg in "$@"; do
        case $arg in
            --dev)
                mode="dev"
                ;;
            --prod)
                mode="prod"
                ;;
            --test)
                mode="test"
                ;;
            --with-init)
                COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.with-init.yml"
                ;;
        esac
    done

    case $mode in
        dev)
            COMPOSE_FILES="$COMPOSE_FILES -f .docker/compose/docker-compose.dev.yml"
            ;;
        prod)
            COMPOSE_FILES="-f .docker/compose/docker-compose.prod.yml"
            ;;
        test)
            COMPOSE_FILES="-f .docker/compose/docker-compose.test.yml"
            ;;
    esac
}

# Main command handling
case "$1" in
    up)
        shift
        parse_mode "$@"
        # Filter out mode flags from service names
        services=""
        for arg in "$@"; do
            case $arg in
                --dev|--prod|--test|--with-init)
                    ;;
                *)
                    services="$services $arg"
                    ;;
            esac
        done

        echo "Starting services with: $COMPOSE_CMD $COMPOSE_FILES"
        $COMPOSE_CMD $COMPOSE_FILES up -d $services

        # Show status
        echo ""
        $COMPOSE_CMD $COMPOSE_FILES ps
        echo ""
        echo "Services started! Access points:"
        echo "  - API: http://localhost:8000"
        echo "  - API Docs: http://localhost:8000/docs"
        echo "  - Datasette: http://localhost:8001"
        echo "  - RQ Dashboard: http://localhost:9181"
        ;;

    down)
        # Find all running compose projects
        $COMPOSE_CMD $COMPOSE_FILES down
        ;;

    build)
        shift
        parse_mode "$@"
        services=""
        for arg in "$@"; do
            case $arg in
                --dev|--prod|--test|--with-init)
                    ;;
                *)
                    services="$services $arg"
                    ;;
            esac
        done
        $COMPOSE_CMD $COMPOSE_FILES build $services
        ;;

    logs)
        shift
        parse_mode "$@"
        service="$1"
        if [ -z "$service" ]; then
            $COMPOSE_CMD $COMPOSE_FILES logs -f
        else
            $COMPOSE_CMD $COMPOSE_FILES logs -f "$service"
        fi
        ;;

    shell)
        shift
        parse_mode "$@"
        service="$1"
        if [ -z "$service" ]; then
            echo "Error: Please specify a service name"
            echo "Example: ./docker.sh shell app"
            exit 1
        fi
        $COMPOSE_CMD $COMPOSE_FILES exec "$service" bash || \
        $COMPOSE_CMD $COMPOSE_FILES exec "$service" sh
        ;;

    exec)
        shift
        parse_mode "$@"
        service="$1"
        shift
        if [ -z "$service" ]; then
            echo "Error: Please specify a service name and command"
            echo "Example: ./docker.sh exec app python --version"
            exit 1
        fi
        $COMPOSE_CMD $COMPOSE_FILES exec "$service" "$@"
        ;;

    ps)
        parse_mode "$@"
        $COMPOSE_CMD $COMPOSE_FILES ps
        ;;

    test)
        echo "Running tests in Docker..."
        $COMPOSE_CMD -f .docker/compose/docker-compose.test.yml run --rm test
        ;;

    clean)
        echo "Stopping services and removing volumes..."
        $COMPOSE_CMD $COMPOSE_FILES down -v
        echo "Clean complete!"
        ;;

    *)
        usage
        exit 1
        ;;
esac