#!/bin/bash
# Health check script for HAARRRvest publisher service
# Checks if the HAARRRvest repository has been successfully cloned

DATA_REPO_PATH="${DATA_REPO_PATH:-/data-repo}"

# Check if the repository directory exists and is a git repository
if [ -d "$DATA_REPO_PATH/.git" ]; then
    # Repository exists, check if it has content
    if [ -d "$DATA_REPO_PATH/daily" ] || [ -f "$DATA_REPO_PATH/README.md" ]; then
        exit 0  # Healthy - repository is cloned and has expected content
    else
        exit 1  # Repository exists but appears empty
    fi
else
    exit 1  # Repository not yet cloned
fi