# GitHub Workflows Guide

This document explains the GitHub Actions workflows in this repository and how to set them up for forks.

## Workflows Overview

### 1. CI (Continuous Integration)
**File**: `.github/workflows/ci.yml`
**Purpose**: Comprehensive testing and code quality checks
**Triggers**: 
- Push to `main` and `develop` branches
- Pull requests to `main` branch
**Fork-friendly**: ✅ Yes - Works automatically in forks

### 2. CD (Continuous Deployment)
**File**: `.github/workflows/cd.yml`
**Purpose**: Builds and pushes Docker images to GitHub Container Registry
**Triggers**:
- Push to `main` branch
- Version tags (`v*`)
- Release publications
- Successful CI workflow completion on `main`
**Fork-friendly**: ✅ Yes - Works automatically in forks

### 3. Claude Code Review
**File**: `.github/workflows/claude-code-review.yml`
**Purpose**: AI-powered code review on pull requests using Claude
**Triggers**: Pull request opened or synchronized to `main` branch
**Fork-friendly**: ❌ No - Restricted to repository owner only

### 4. Claude Code
**File**: `.github/workflows/claude.yml`
**Purpose**: Interactive AI assistant for issues and PR comments
**Triggers**: 
- Issue comments containing `@claude`
- PR review comments containing `@claude`
- New issues containing `@claude`
**Fork-friendly**: ❌ No - Restricted to repository owner only

## Setting Up Workflows in Your Fork

### Required Secrets and Variables

To use the workflows in your fork, configure the following:

#### Repository Secrets
1. **For CI Testing (Optional)**:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key for LLM tests
   - Tests will run without this but skip LLM-dependent tests

2. **For Claude Workflows** (Main repository only):
   - `CLAUDE_CODE_OAUTH_TOKEN`: OAuth token from Claude Code GitHub integration
   - These workflows are restricted to the main repository owner

#### Environment Configuration
The CI workflow uses these environments:
- **`ci` environment**: For running tests (created automatically)
- **`production` environment**: For CD deployment (manual setup required)

### Setup Instructions

1. **Fork the repository**
   ```bash
   # Fork via GitHub UI, then clone
   git clone https://github.com/YOUR_USERNAME/pantry-pirate-radio.git
   cd pantry-pirate-radio
   ```

2. **Local Development Setup**:
   ```bash
   # Use bouy for initial setup
   ./bouy setup                 # Interactive setup wizard
   ./bouy up                    # Start services
   ./bouy test                  # Run all tests locally
   ```

3. **Configure GitHub Actions Secrets** (optional):
   - Go to Settings → Secrets and variables → Actions
   - Add `OPENROUTER_API_KEY` if you want full LLM testing in CI

4. **Disable Claude workflows** (recommended for forks):
   - The Claude workflows won't run in forks by design
   - Optionally remove `.github/workflows/claude*.yml` files

5. **Configure Docker registry** (automatic for forks):
   - The CD workflow automatically pushes to GitHub Container Registry
   - Images will be published to `ghcr.io/YOUR_USERNAME/pantry-pirate-radio`
   - No additional configuration needed - uses `GITHUB_TOKEN`

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

The CI workflow consists of multiple parallel jobs for efficiency:

### Jobs Structure
1. **setup**: Generates cache keys for dependency caching
2. **formatting-and-linting**: Black formatting and Ruff linting checks
3. **mypy**: Type checking with MyPy
4. **pytest**: Full test suite using bouy in Docker
5. **vulture**: Dead code detection  
6. **bandit**: Security vulnerability scanning
7. **safety**: Dependency vulnerability checks
8. **pip-audit**: Additional dependency auditing
9. **xenon**: Code complexity analysis
10. **bouy-tests**: Tests the bouy CLI tool itself

### Test Execution with Bouy
The pytest job uses bouy for test execution:
```bash
# CI runs tests using bouy's programmatic mode
./bouy --programmatic test --pytest
```

This ensures:
- Consistent test environment between local and CI
- Proper Docker container management
- Coverage report generation (XML and JSON formats)
- Coverage ratcheting to prevent regression

### Coverage Baseline
- Coverage baselines are cached between runs
- Main branch updates create new baselines
- Pull requests compare against main's baseline
- Prevents coverage from decreasing

No additional setup required for the CI workflow in forks.

## CD Workflow Details

The CD workflow builds and publishes two types of Docker images:

### 1. Unified Application Image
- **Target**: `unified` stage from Dockerfile
- **Contains**: All services (API, worker, scrapers, etc.)
- **Platform**: linux/amd64
- **Tags**:
  - `latest` and `main` for main branch
  - `v*` and `stable` for version tags
  - Date-based tags (YYYYMMDD)
  - SHA-based tags for traceability

### 2. Datasette Image
- **Purpose**: SQLite data viewer for HAARRRvest data
- **Platform**: linux/amd64
- **Tags**: 
  - `datasette-latest` for main branch
  - `datasette-YYYYMMDD` date-based
  - `datasette-SHA` for specific commits

### Deployment Triggers
- Direct pushes to `main` branch
- Version tags (`v1.0.0`, `v2.1.3`, etc.)
- GitHub release publications
- Successful CI workflow completion on `main`

### Image Registry
- Automatically publishes to GitHub Container Registry
- Images available at `ghcr.io/YOUR_USERNAME/pantry-pirate-radio`
- No additional configuration needed for forks
- Uses `GITHUB_TOKEN` for authentication (provided automatically)

## Contributing Back

When contributing to the main repository:

1. **CI Checks**: All CI jobs must pass on your pull request
2. **Test Coverage**: Ensure coverage doesn't decrease
3. **Code Quality**: Follow black formatting and ruff linting rules
4. **Type Safety**: Fix any mypy type errors
5. **Security**: Address any bandit or safety findings
6. **Claude Review**: May automatically review PRs to main branch
7. **Manual Review**: Repository maintainers will review your changes

### Using Bouy for Local Testing
Before pushing changes, run locally:
```bash
# Run all CI checks locally
./bouy test

# Or run specific checks
./bouy test --pytest         # Tests only
./bouy test --mypy           # Type checking
./bouy test --black          # Formatting
./bouy test --ruff           # Linting
./bouy test --bandit         # Security
```

## Workflow Environment Variables

The CI workflow sets these environment variables:
```yaml
POSTGRES_USER: postgres
POSTGRES_PASSWORD: pirate
POSTGRES_DB: pantry_pirate_radio
DATABASE_URL: postgresql://postgres:pirate@db:5432/pantry_pirate_radio
REDIS_URL: redis://cache:6379/0
LLM_PROVIDER: openai
LLM_MODEL_NAME: google/gemini-2.0-flash-001
CI: true  # Skips heavy database initialization
```

## Permissions Required

### CI Workflow
- `contents: read` - Read repository code
- `actions: read` - Read workflow status
- `checks: write` - Update check status
- `packages: write` - For pytest job (Docker image caching)

### CD Workflow
- `contents: read` - Read repository code
- `packages: write` - Push Docker images
- `id-token: write` - OIDC token for secure deployments

### Claude Workflows
- `contents: read` - Read repository code
- `pull-requests: read/write` - Comment on PRs
- `issues: read` - Read issue content
- `actions: read` - Read CI results

## Questions?

If you have questions about the workflows:
1. Check the workflow files for detailed inline documentation
2. Use `./bouy --help` for local development commands
3. Open an issue for clarification
4. See CONTRIBUTING.md for contribution guidelines
5. Review CLAUDE.md for AI pair programming setup