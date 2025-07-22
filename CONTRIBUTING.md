# Contributing to Pantry Pirate Radio

We welcome contributions to Pantry Pirate Radio! This guide will help you get started with contributing to our AI-powered food security data aggregation system while maintaining our high security and code quality standards.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Security Requirements](#security-requirements)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Types of Contributions](#types-of-contributions)
- [Architecture Overview](#architecture-overview)
- [Common Development Tasks](#common-development-tasks)

## Code of Conduct

This project is committed to fostering a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.11+
- Poetry
- Docker and Docker Compose
- PostgreSQL with PostGIS (handled by Docker)
- Redis 7.0+ (handled by Docker)

### Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/***REMOVED_USER***/pantry-pirate-radio.git
   cd pantry-pirate-radio
   ```

2. **Install dependencies and set up security**:
   ```bash
   # Install dependencies
   poetry install

   # Set up environment variables
   cp .env.example .env
   # Edit .env with your configuration

   # Enable git hooks for security
   git config core.hooksPath .githooks
   ```

3. **Start all services**:
   ```bash
   docker-compose up -d
   ```

4. **Verify setup**:
   - FastAPI server: http://localhost:8000
   - API docs: http://localhost:8000/docs
   - RQ Dashboard: http://localhost:9181

## Security Requirements

**Security is a top priority for this project.** Before contributing, please familiarize yourself with our security guidelines:

### 1. **Never Commit Secrets**
- Never commit API keys, passwords, or other sensitive information
- Use environment variables for all secrets
- The pre-commit hook will prevent most accidental commits

### 2. **Test Data Guidelines**
When adding test data, always use anonymized information:
- **Phone Numbers**: Use `555-xxx-xxxx` format only
- **Email Addresses**: Use `example.com`, `test.com`, or `localhost` domains
- **Addresses**: Use obviously fake addresses like `123 Test Street, Example City, ST 12345`
- **Names**: Use placeholder names like `John Doe`, `Jane Smith`, or `Test Organization`

### 3. **Data File Security**
- Never commit real personal information (PII)
- Review all CSV, JSON, and other data files for real data
- Use minimal test datasets
- Document the source and purpose of any data files

### 4. **Code Security**
- Use environment variables for configuration
- Validate all user inputs
- Follow secure coding practices

### 5. **GitHub Workflows**
- The Claude AI workflows are restricted to the repository owner only
- These workflows use expensive API calls and will not run on forks
- See [GitHub Workflows Guide](docs/GITHUB_WORKFLOWS.md) for details on setting up workflows in your fork
- Use type hints for better code safety

### Pre-commit Hooks

Our pre-commit hooks automatically check for:
- Secrets and API keys
- Personal identifiable information (PII)
- Hardcoded credentials
- Sensitive file patterns
- Real phone numbers and email addresses

If the hook fails, review the output and fix the issues before committing.

### Security Incident Response

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Report privately to maintainers via GitHub private message
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

## Making Changes

### Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following our code style guidelines and security requirements

3. **Run comprehensive quality checks**:
   ```bash
   # Run all tests
   poetry run pytest

   # Run type checking
   poetry run mypy .

   # Run security scanning
   poetry run bandit -r app/

   # Run code formatting
   poetry run black .
   poetry run ruff .
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```
   The pre-commit hook will automatically run security checks.

## Code Style Guidelines

### Python Code Style

- **Formatting**: Black with 88 character line length
- **Linting**: Ruff with security checks
- **Type Checking**: mypy with strict configuration
- **Documentation**: Docstrings required for all public functions
- **Import Organization**: isort for consistent imports

### Code Quality Standards

- **Test Coverage**: Minimum 90% coverage required
- **Type Safety**: All functions must have type annotations
- **Security**: Bandit security scanning must pass
- **Documentation**: Clear docstrings and inline comments

### Running Quality Checks

```bash
# Format code
poetry run black .

# Check linting
poetry run ruff .

# Type checking
poetry run mypy .

# Security scan
poetry run bandit -r app/

# Check unused code
poetry run vulture app/

# All quality checks
poetry run pytest --cov
```

## Testing

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov

# Run specific test file
poetry run pytest tests/test_filename.py

# Run integration tests
poetry run pytest -m integration

# Run async tests
poetry run pytest -m asyncio

# Test scrapers
python -m app.scraper.test_scrapers --all
```

### Test Categories

- **Unit Tests**: Test individual components
- **Integration Tests**: Test service interactions
- **Property-based Tests**: Using Hypothesis for edge cases
- **Scraper Tests**: Validation of data collection

### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names
- Include both positive and negative test cases
- Mock external dependencies
- Use pytest fixtures for common setup

## Submitting Changes

### Pull Request Process

1. **Ensure all tests pass**:
   ```bash
   poetry run pytest --cov
   ```

2. **Verify code quality and security**:
   ```bash
   poetry run mypy .
   poetry run ruff .
   poetry run black . --check
   poetry run bandit -r app/
   ```

3. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a pull request** using our template

### Pull Request Guidelines

#### Required Checks
- [ ] All tests pass
- [ ] Type checking passes
- [ ] Security scanning passes
- [ ] Code formatting is correct
- [ ] No secrets or PII in code/data
- [ ] Documentation is updated

#### Pull Request Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Security Checklist
- [ ] No secrets committed
- [ ] Test data is anonymized
- [ ] Security scanning passes
- [ ] PII detection passes

## Testing
- [ ] Tests added/updated
- [ ] All tests pass
- [ ] Manual testing completed

## Documentation
- [ ] Code comments added
- [ ] Documentation updated
- [ ] API documentation updated (if applicable)
```

### Pull Request Best Practices

- Keep changes focused and atomic
- Include tests for new functionality
- Update documentation as needed
- Maintain backwards compatibility
- Follow semantic commit messages

## Types of Contributions

### Bug Fixes

- Include reproduction steps
- Add regression tests
- Reference issue numbers
- Ensure security implications are considered

### New Features

- Discuss major features in an issue first
- Include comprehensive tests
- Update documentation
- Consider impact on existing functionality
- Follow security guidelines

### Documentation

- Use clear, concise language
- Include code examples
- Update API documentation
- Check for broken links

### Scrapers

- Inherit from `ScraperJob` base class
- Include comprehensive error handling
- Follow rate limiting best practices
- Add tests in `test_scrapers.py`
- Use anonymized test data only

## Architecture Overview

### Core Services

- **FastAPI App**: API server with HSDS-compliant endpoints
- **Worker Pool**: LLM-based data processing
- **Reconciler**: Data consistency and versioning
- **Recorder**: Job result archival
- **Scrapers**: Data collection from various sources

### Key Components

- **HSDS Models**: Pydantic models for data validation
- **LLM Integration**: AI-powered data normalization
- **Geographic Data**: PostGIS spatial queries
- **Queue System**: Redis-based job processing

### Security Architecture

- **Input Validation**: All user inputs are validated
- **Environment Variables**: Secrets stored in environment
- **Audit Logging**: Comprehensive logging with correlation IDs
- **Access Control**: No authentication required (public data only)

## Common Development Tasks

### Adding a New Scraper

1. Create `your_scraper_name_scraper.py` in `app/scraper/`
2. Inherit from `ScraperJob` base class
3. Implement `scrape()` method
4. Add comprehensive error handling
5. Include tests in `test_scrapers.py`
6. Add documentation in `your_scraper_name_scraper.md`
7. Use only anonymized test data

### Modifying HSDS Models

1. Update Pydantic models in `app/models/hsds/`
2. Run database migrations if needed
3. Update API endpoints
4. Add validation tests
5. Update documentation
6. Consider security implications

### Adding LLM Provider

1. Implement `BaseLLMProvider` in `app/llm/providers/`
2. Add provider configuration
3. Include caching and retry logic
4. Write integration tests
5. Ensure API keys are stored securely

### Database Schema Changes

1. Create migration scripts in `init-scripts/`
2. Update SQLAlchemy models if needed
3. Update reconciler logic for new fields
4. Add validation tests
5. Update API responses
6. Consider backward compatibility

## Environment Variables

### Required
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string

### Optional
- `OPENROUTER_API_KEY`: For OpenAI/OpenRouter providers
- `LLM_MODEL_NAME`: Default LLM model
- `OUTPUT_DIR`: Directory for output files
- `BACKUP_KEEP_DAYS`: Database backup retention days

## Service URLs (Development)
- FastAPI API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- RQ Dashboard: http://localhost:9181
- Datasette: http://localhost:8001
- Prometheus Metrics: http://localhost:8000/metrics

## Getting Help

- **Issues**: Report bugs or request features
- **Discussions**: Ask questions about development
- **Documentation**: Check the `docs/` directory and `CLAUDE.md`
- **Code Review**: All PRs receive thorough review
- **Security**: Follow security reporting guidelines for vulnerabilities

## Key Dependencies

- FastAPI for API framework
- Pydantic for data validation
- SQLAlchemy for database ORM
- Redis for job queues
- PostGIS for geographic data
- OpenAI for LLM processing
- Prometheus for metrics
- Docker/Docker Compose for containerization

## License

By contributing to Pantry Pirate Radio, you agree that your contributions will be released into the public domain under the Unlicense.

---

Thank you for contributing to Pantry Pirate Radio! Your efforts help make food security resources more accessible to everyone while maintaining the highest standards of security and code quality.