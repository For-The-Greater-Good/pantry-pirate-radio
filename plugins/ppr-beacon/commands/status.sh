#!/usr/bin/env bash
# Show build statistics
set -euo pipefail

$COMPOSE_CMD $COMPOSE_FILES run --rm --profile beacon beacon python -m app.cli status
