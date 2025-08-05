#!/bin/bash
# Run the content store dashboard

echo "Starting Content Store Dashboard..."
echo "The dashboard will be available at http://localhost:5050"
echo ""

exec ./bouy exec app python -m app.content_store dashboard "$@"