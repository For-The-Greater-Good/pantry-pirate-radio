#!/bin/bash
# Script to update CORS configuration for production API

# Add these environment variables to your production deployment:
export CORS_ORIGINS='["*"]'  # Allow all origins for development
# Or for specific origins:
# export CORS_ORIGINS='["http://localhost:3000", "http://ubuntu-runner:3000", "https://foodito.app"]'

echo "CORS configuration to add to production:"
echo "================================"
echo "Option 1 - Allow all origins (for development):"
echo "  CORS_ORIGINS='[\"*\"]'"
echo ""
echo "Option 2 - Specific origins:"
echo "  CORS_ORIGINS='[\"http://localhost:3000\", \"http://ubuntu-runner:3000\", \"https://foodito.app\"]'"
echo ""
echo "Add one of these to your production environment variables and redeploy."