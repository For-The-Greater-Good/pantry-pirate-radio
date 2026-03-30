#!/usr/bin/env bash
# Build static site pages
# Usage: ./bouy beacon build [OPTIONS]
#   --location ID    Build single location (preview mode)
#   --state STATE    Build all locations in a state
#   --incremental    Only rebuild changed pages
set -euo pipefail

$COMPOSE_CMD $COMPOSE_FILES run --rm --profile beacon beacon python -m app.cli build "$@"
