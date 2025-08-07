# Contributing to Pantry Pirate Radio

We welcome contributions to Pantry Pirate Radio! This guide will help you get started with contributing to our AI-powered food security data aggregation system while maintaining our high security and code quality standards.

> **📚 Documentation**: For comprehensive project documentation including architecture, API reference, scrapers, and deployment guides, visit our **[Documentation Hub](docs/INDEX.md)**.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Security Requirements](#security-requirements)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style Guidelines](#code-style-guidelines)
- [Submitting Changes](#submitting-changes)
- [Types of Contributions](#types-of-contributions)
- [Architecture Overview](#architecture-overview)
- [Common Development Tasks](#common-development-tasks)

## Code of Conduct

This project is committed to fostering a welcoming and inclusive environment. Please be respectful and constructive in all interactions. We welcome contributors from all backgrounds and experience levels.

## Getting Started

### Prerequisites

**IMPORTANT**: You only need Docker installed. All other dependencies are managed within containers.

- Docker and Docker Compose (required)
- Git (required)
- No local Python installation needed
- No local PostgreSQL or Redis needed

### Quick Start

```bash
# Clone the repository
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Run interactive setup wizard
./bouy setup

# Start services
./bouy up

# Run tests to verify setup
./bouy test
```

## Development Setup

### 1. Fork and Clone

```bash
# Fork via GitHub UI, then:
git clone https://github.com/YOUR_USERNAME/pantry-pirate-radio.git
cd pantry-pirate-radio
```

### 2. Initial Configuration

```bash
# Run the interactive setup wizard
./bouy setup

# This will:
# - Create .env from template
# - Configure database passwords
# - Set up LLM provider (OpenAI/Claude)
# - Configure API keys
# - Create backups of existing .env files
```

### 3. Start Development Environment

```bash
# Start all services in development mode
./bouy up

# Or start with database initialization
./bouy up --with-init

# Check service status
./bouy ps
```

### 4. Verify Setup

Once services are running:
- **API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **RQ Dashboard**: http://localhost:9181
- **Datasette** (production mode): http://localhost:8001

## Security Requirements

**Security is our top priority.** Please follow these guidelines:

### Never Commit Secrets

1. **Use bouy setup**: Run `./bouy setup` to configure secrets safely
2. **Environment variables**: All secrets must use environment variables
3. **Check before commit**: Review all changes for hardcoded credentials
4. **Use .env files**: Never commit `.env` files to version control

### Test Data Security

When adding test data, **always use fictional information**:

- **Phone Numbers**: Use `555-xxx-xxxx` format only
- **Email Addresses**: Use `example.com`, `test.com`, or `localhost` domains
- **Addresses**: Use clearly fake addresses like `123 Test Street, Example City, ST 12345`
- **Names**: Use placeholder names like `John Doe`, `Jane Smith`, `Test Organization`
- **URLs**: Use `example.com` or `localhost` for test URLs

### Security Testing

```bash
# Run security checks
./bouy test --bandit         # Security linting
./bouy test --safety         # Dependency vulnerabilities
./bouy test --pip-audit      # Package auditing

# Run all security and quality checks
./bouy test                  # Comprehensive test suite
```

### Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Use GitHub Security Advisories (private)
3. Include:
   - Description of the vulnerability
   - Steps to reproduce using bouy commands
   - Potential impact assessment
   - Suggested fix (if known)

## Making Changes

### Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # Or for fixes:
   git checkout -b fix/issue-description
   ```

2. **Make your changes** following TDD principles:
   ```bash
   # Write tests first
   ./bouy shell app
   # Create/edit test files
   
   # Run tests (should fail)
   ./bouy test --pytest tests/test_your_feature.py
   
   # Implement feature
   # Edit source files
   
   # Run tests again (should pass)
   ./bouy test --pytest tests/test_your_feature.py
   ```

3. **Run quality checks**:
   ```bash
   # Run all tests and checks
   ./bouy test
   
   # Or run specific checks:
   ./bouy test --pytest         # Unit tests
   ./bouy test --mypy           # Type checking
   ./bouy test --black          # Formatting
   ./bouy test --ruff           # Linting
   ./bouy test --bandit         # Security
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   # Use conventional commits:
   # feat: new feature
   # fix: bug fix
   # docs: documentation
   # test: testing
   # refactor: code refactoring
   ```

## Testing

### Test-Driven Development (TDD)

This project follows TDD principles:

1. **Red**: Write a failing test that defines desired behavior
2. **Green**: Write minimal code to make the test pass
3. **Refactor**: Improve code while keeping tests passing

### Running Tests

```bash
# Run all tests with coverage
./bouy test

# Run specific test categories
./bouy test --pytest         # Python tests with coverage
./bouy test --mypy           # Type checking
./bouy test --black          # Code formatting
./bouy test --ruff           # Linting
./bouy test --bandit         # Security analysis
./bouy test --coverage       # Coverage threshold check

# Run specific test files
./bouy test --pytest tests/test_api.py
./bouy test --pytest tests/test_scraper/

# Run with additional pytest options
./bouy test --pytest -- -v                    # Verbose
./bouy test --pytest -- -x                    # Stop on first failure
./bouy test --pytest -- -k test_name          # Run specific test
./bouy test --pytest -- --pdb                 # Debug on failure
```

### Using @agent-test-suite-monitor

For comprehensive test monitoring, use the dedicated test agent:

```bash
# Examples of when to use the test monitor agent:
@agent-test-suite-monitor "Run full test suite after implementing new API endpoint"
@agent-test-suite-monitor "Debug failing geocoding tests"
@agent-test-suite-monitor "Check test coverage after refactoring"
```

### Coverage Requirements

- Minimum coverage: 90%
- View coverage report: `open htmlcov/index.html`
- Check coverage: `./bouy test --coverage`

## Code Style Guidelines

### Python Standards

- **Formatting**: Black (88 character line length)
- **Linting**: Ruff with security rules
- **Type Hints**: Required for all functions
- **Docstrings**: Required for public functions
- **Imports**: Organized with isort

### Running Code Quality Checks

```bash
# Auto-format code
./bouy test --black

# Check types
./bouy test --mypy

# Lint code
./bouy test --ruff

# Security scan
./bouy test --bandit

# Find dead code
./bouy test --vulture

# Check complexity
./bouy test --xenon
```

## Submitting Changes

### Pull Request Process

1. **Ensure all tests pass**:
   ```bash
   ./bouy test
   ```

2. **Update documentation** if needed:
   - API documentation (docstrings)
   - README files
   - Configuration examples
   - See [Documentation Hub](docs/INDEX.md) for documentation structure

3. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create Pull Request** via GitHub UI

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change)
- [ ] New feature (non-breaking change)
- [ ] Breaking change (fix or feature with breaking changes)
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] All tests pass: `./bouy test`
- [ ] Coverage maintained above 90%
- [ ] Manual testing completed

## Security Checklist
- [ ] No secrets or credentials in code
- [ ] Test data uses fictional information only
- [ ] Security scan passes: `./bouy test --bandit`
- [ ] No PII in test files

## Documentation
- [ ] Code includes docstrings
- [ ] README updated (if needed)
- [ ] API docs updated (if applicable)
```

### Branch Protection

Pull requests to `main` require:
- All CI checks passing
- Code review approval
- No merge conflicts
- Up-to-date with main branch

## Types of Contributions

### Bug Fixes

1. Create issue describing the bug
2. Write test that reproduces the bug
3. Fix the bug
4. Ensure test passes
5. Submit PR with fix and test

### New Features

1. Discuss in issue first (for major features)
2. Write comprehensive tests using TDD
3. Implement feature
4. Update documentation
5. Submit PR with tests and docs

### New Scrapers

```bash
# Test existing scraper
./bouy scraper-test NAME

# Run scraper
./bouy scraper NAME

# Run all scrapers
./bouy scraper --all

# Parallel execution
./bouy scraper scouting-party
```

When adding a scraper:
1. Inherit from `ScraperJob` base class
2. Implement rate limiting
3. Add error handling
4. Write tests with mock data
5. Document in `docs/scrapers/`

### Documentation

- Use clear, concise language
- Include code examples
- Test all code snippets
- Update relevant README files

## Architecture Overview

### Core Services

Managed via bouy commands:

- **API Server**: FastAPI with HSDS endpoints
- **Worker Pool**: LLM data processing queue
- **Reconciler**: Data deduplication and versioning
- **Scrapers**: Public data collection
- **Content Store**: Deduplicated storage

### Key Technologies

- **FastAPI**: REST API framework
- **Pydantic**: Data validation
- **SQLAlchemy**: Database ORM
- **PostgreSQL/PostGIS**: Spatial database
- **Redis**: Job queue and caching
- **Docker**: Containerization

## Common Development Tasks

### Working with Services

```bash
# View logs
./bouy logs app              # Single service
./bouy logs                  # All services

# Access shell
./bouy shell app             # Bash/sh in container
./bouy exec app python       # Run Python

# Restart services
./bouy down && ./bouy up
```

### Database Operations

```bash
# Initialize database
./bouy up --with-init

# Access database
./bouy shell db
psql -U postgres -d pantry_pirate_radio

# Run migrations
./bouy exec app python -m app.database
```

### Scraper Development

```bash
# List available scrapers
./bouy scraper --list

# Test scraper (dry run)
./bouy scraper-test freshtrak

# Run single scraper
./bouy scraper freshtrak

# Run all scrapers
./bouy scraper --all
```

### LLM Configuration

```bash
# Configure via setup
./bouy setup

# Or set in .env:
# LLM_PROVIDER=openai
# OPENROUTER_API_KEY=your-key
# LLM_MODEL_NAME=model-name
```

## Environment Variables

### Essential Configuration

Set via `./bouy setup` or `.env` file:

```bash
# Database (default provided)
DATABASE_URL=postgresql://postgres:pirate@db:5432/pantry_pirate_radio
REDIS_URL=redis://cache:6379/0

# LLM Configuration
LLM_PROVIDER=openai
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL_NAME=google/gemini-flash-1.5-8b

# Optional
OUTPUT_DIR=/app/outputs
HAARRRVEST_REPO_TOKEN=token_or_skip
```

## Getting Help

- **Documentation**: Check `/docs` directory and CLAUDE.md
- **Issues**: Report bugs or request features on GitHub
- **Discussions**: Ask questions in GitHub Discussions
- **Code Review**: All PRs receive thorough review
- **Real-time Help**: Use @agent mentions in issues/PRs

## CI/CD Pipeline

Our CI pipeline automatically runs on all PRs:

1. **Formatting and Linting**: Black, Ruff
2. **Type Checking**: Mypy
3. **Security Scanning**: Bandit, Safety, Pip-audit
4. **Testing**: Pytest with coverage
5. **Code Quality**: Vulture, Xenon
6. **Docker Build**: Validates container builds

## License

By contributing to Pantry Pirate Radio, you agree that your contributions will be released into the public domain under the Unlicense.

---

Thank you for contributing to Pantry Pirate Radio! Your efforts help make food security resources more accessible to everyone. Remember to use bouy commands for all development tasks - it ensures consistency and handles all Docker complexity for you.