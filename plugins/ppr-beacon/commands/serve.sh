#!/usr/bin/env bash
# Serve generated pages locally for preview
# Usage: ./bouy beacon serve [--port PORT]
set -euo pipefail

PORT="${1:-8888}"
$COMPOSE_CMD $COMPOSE_FILES run --rm --profile beacon -p "${PORT}:8888" beacon \
  python -m http.server 8888 --directory /app/output
