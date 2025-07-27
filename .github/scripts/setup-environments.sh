#!/bin/bash

# GitHub Repository Environment Setup Script
# This script recreates the environments configuration for the repository

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed${NC}"
    echo "Please install it from: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with GitHub${NC}"
    echo "Please run: gh auth login"
    exit 1
fi

# Get repository name from git remote or argument
if [ -z "$1" ]; then
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
    if [ -z "$REPO" ]; then
        echo -e "${RED}Error: Could not determine repository${NC}"
        echo "Usage: $0 [owner/repo]"
        exit 1
    fi
else
    REPO="$1"
fi

echo -e "${GREEN}Setting up environments for repository: $REPO${NC}"

# Function to create or update environment
create_environment() {
    local env_name="$1"
    local protection_rules="$2"
    local deployment_branch_policy="$3"

    echo -e "\n${YELLOW}Configuring environment: $env_name${NC}"

    # Create environment
    gh api "repos/$REPO/environments/$env_name" \
        --method PUT \
        --field "deployment_branch_policy=$deployment_branch_policy" \
        2>/dev/null || true

    # Add protection rules if specified
    if [ -n "$protection_rules" ]; then
        gh api "repos/$REPO/environments/$env_name" \
            --method PUT \
            --input - <<< "$protection_rules"
    fi

    echo -e "${GREEN}✓ Environment '$env_name' configured${NC}"
}

# Create CI environment
echo -e "\n${YELLOW}Creating 'ci' environment...${NC}"
ci_config=$(cat <<EOF
{
  "deployment_branch_policy": null,
  "protection_rules": []
}
EOF
)
create_environment "ci" "" "$ci_config"

# Create Production environment with protection
echo -e "\n${YELLOW}Creating 'production' environment...${NC}"
prod_config=$(cat <<EOF
{
  "protection_rules": [
    {
      "type": "required_reviewers",
      "reviewers": []
    },
    {
      "type": "wait_timer",
      "wait_timer": 0
    }
  ],
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
EOF
)

# First create the environment
gh api "repos/$REPO/environments/production" \
    --method PUT \
    --field 'deployment_branch_policy[protected_branches]=false' \
    --field 'deployment_branch_policy[custom_branch_policies]=true' \
    2>/dev/null || true

# Then add deployment branch policy for main branch
echo -e "${YELLOW}Adding deployment branch policy for 'main' branch...${NC}"
gh api "repos/$REPO/environments/production/deployment-branch-policies" \
    --method POST \
    --field 'name=main' \
    --field 'type=branch' \
    2>/dev/null || true

echo -e "${GREEN}✓ Environment 'production' configured with branch protection${NC}"

# List all environments
echo -e "\n${GREEN}Current environments:${NC}"
gh api "repos/$REPO/environments" --jq '.environments[] | "- \(.name) (protection rules: \(.protection_rules | length))"'

# Instructions for secrets
echo -e "\n${YELLOW}📝 Manual Steps Required:${NC}"
echo -e "\nThe following secrets need to be manually added to the repository:"
echo -e "1. ${GREEN}OPENROUTER_API_KEY${NC} - Your OpenRouter API key"
echo -e "2. ${GREEN}CLAUDE_CODE_OAUTH_TOKEN${NC} - Claude Code OAuth token"
echo -e "\nTo add secrets:"
echo -e "  gh secret set OPENROUTER_API_KEY --body 'your-key-here' --repo $REPO"
echo -e "  gh secret set CLAUDE_CODE_OAUTH_TOKEN --body 'your-token-here' --repo $REPO"
echo -e "\nOr via GitHub UI:"
echo -e "  https://github.com/$REPO/settings/secrets/actions"

# Environment-specific variables (if needed)
echo -e "\n${YELLOW}Environment Variables:${NC}"
echo -e "You can also set environment-specific variables:"
echo -e "  gh api repos/$REPO/environments/production/variables \\"
echo -e "    --method POST \\"
echo -e "    --field name=VARIABLE_NAME \\"
echo -e "    --field value=variable_value"