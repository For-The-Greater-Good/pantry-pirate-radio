#!/bin/bash
set -e

# Build all Docker images
echo "Building all Docker images..."

# Build main app image with all targets
docker build \
  --target production-base \
  -t pantry-pirate-radio:production-base \
  -f .docker/images/app/Dockerfile \
  .

docker build \
  --target app \
  -t pantry-pirate-radio:app \
  -f .docker/images/app/Dockerfile \
  .

docker build \
  --target worker \
  -t pantry-pirate-radio:worker \
  -f .docker/images/app/Dockerfile \
  .

docker build \
  --target recorder \
  -t pantry-pirate-radio:recorder \
  -f .docker/images/app/Dockerfile \
  .

docker build \
  --target scraper \
  -t pantry-pirate-radio:scraper \
  -f .docker/images/app/Dockerfile \
  .

docker build \
  --target test \
  -t pantry-pirate-radio:test \
  -f .docker/images/app/Dockerfile \
  .

# Build datasette image
docker build \
  -t pantry-pirate-radio:datasette \
  -f .docker/images/datasette/Dockerfile \
  .

echo "All images built successfully!"
docker images | grep pantry-pirate-radio