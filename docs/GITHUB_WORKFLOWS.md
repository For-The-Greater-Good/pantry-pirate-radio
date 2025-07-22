# GitHub Workflows Guide

This document explains the GitHub Actions workflows in this repository and how to set them up for forks.

## Workflows Overview

### 1. CI (Continuous Integration)
**File**: `.github/workflows/ci.yml`
**Purpose**: Runs tests, linting, type checking, and security scans on every push and pull request.
**Fork-friendly**: ✅ Yes - Works automatically in forks

### 2. CD (Continuous Deployment)
**File**: `.github/workflows/cd.yml`
**Purpose**: Builds and pushes Docker images to GitHub Container Registry
**Fork-friendly**: ✅ Yes - But requires setup (see below)

### 3. Claude Code Review
**File**: `.github/workflows/claude-code-review.yml`
**Purpose**: AI-powered code review on pull requests
**Fork-friendly**: ❌ No - Restricted to repository owner only

### 4. Claude Code
**File**: `.github/workflows/claude.yml`
**Purpose**: AI assistant for issues and pull requests
**Fork-friendly**: ❌ No - Restricted to repository owner only

## Setting Up Workflows in Your Fork

### Required Secrets

To use the workflows in your fork, you'll need to set up the following GitHub secrets:

1. **For LLM Processing (Workers)**:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key for OpenAI models
   - OR configure Claude authentication (see Claude setup guide)

2. **For Claude Workflows** (Not available in forks):
   - `CLAUDE_CODE_OAUTH_TOKEN`: OAuth token for Claude
   - These workflows are restricted to the main repository owner due to API costs.

### Setup Instructions

1. **Fork the repository**
   ```bash
   # Fork via GitHub UI, then clone
   git clone https://github.com/YOUR_USERNAME/pantry-pirate-radio.git
   ```

2. **Set up secrets in your fork**:
   - Go to Settings → Secrets and variables → Actions
   - Add the required secrets listed above

3. **Disable Claude workflows** (if desired):
   - The Claude workflows won't run in forks by design
   - You can delete `.github/workflows/claude*.yml` files if you prefer

4. **Configure Docker registry** (for CD workflow):
   - The CD workflow pushes to GitHub Container Registry
   - Ensure you have package write permissions in your fork

## Workflow Restrictions

### Why Claude Workflows Are Restricted

The Claude workflows (`claude.yml` and `claude-code-review.yml`) are restricted to the repository owner because:

1. **API Costs**: Claude API calls are expensive and limited
2. **Security**: Prevents potential abuse of API credentials
3. **Resource Management**: Ensures sustainable use of AI resources

These workflows check:
- `github.actor == 'For-The-Greater-Good'`
- `github.repository_owner == 'For-The-Greater-Good'`

### Running Your Own AI Workflows

If you want AI-powered workflows in your fork:

1. **Option 1**: Use your own Claude credentials. These credientials were configured using claude code's github setup command.
   - Modify the workflow conditions to check for your username
   - Add your own `CLAUDE_CODE_OAUTH_TOKEN` secret
   - Be aware of API costs!

2. **Option 2**: Use alternative AI services
   - Replace Claude with OpenAI, Anthropic API, or other services
   - Modify the workflows accordingly

3. **Option 3**: Use the LLM processing in the application
   - The main application supports both OpenAI and Claude
   - Configure via environment variables

## CI Workflow Details

The CI workflow runs automatically and includes:

- **Testing**: Full test suite with coverage reporting
- **Type Checking**: MyPy static type analysis
- **Linting**: Ruff for code quality
- **Security**: Bandit for security issues
- **Dependencies**: Safety and pip-audit for vulnerable packages

No additional setup required for the CI workflow in forks.

## CD Workflow Details

The CD workflow:
- Triggers on pushes to `main` branch
- Builds multi-architecture Docker images
- Pushes to GitHub Container Registry

To use in your fork:
1. Ensure GitHub Packages is enabled
2. The workflow should work automatically
3. Images will be published to `ghcr.io/YOUR_USERNAME/pantry-pirate-radio`

## Contributing Back

When contributing to the main repository:

1. The CI workflow will run on your pull request
2. Claude review may run if the repository owner triggers it
3. Follow the contribution guidelines in CONTRIBUTING.md
4. Ensure all CI checks pass before requesting review

## Questions?

If you have questions about the workflows:
1. Check the workflow files for inline documentation
2. Open an issue for clarification
3. See CONTRIBUTING.md for general contribution guidelines