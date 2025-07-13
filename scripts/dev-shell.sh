#!/bin/bash
set -e

# Enter the development container shell
echo "Entering development container shell..."
docker compose exec app /bin/bash
