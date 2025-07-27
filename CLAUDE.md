# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Test-Driven Development (TDD) Workflow

This project follows Test-Driven Development principles. Always write tests before implementing features:

1. **Red Phase**: Write a failing test that defines the desired behavior
2. **Green Phase**: Write the minimum code necessary to make the test pass
3. **Refactor Phase**: Improve the code while keeping tests passing

#### TDD Process for New Features
```bash
# 1. Create test file first
touch tests/test_new_feature.py

# 2. Write failing test
poetry run pytest tests/test_new_feature.py -v  # Should fail

# 3. Implement minimal code to pass
# ... write implementation ...

# 4. Run test again
poetry run pytest tests/test_new_feature.py -v  # Should pass

# 5. Refactor and ensure tests still pass
poetry run pytest tests/test_new_feature.py -v

# 6. Run full test suite before committing
poetry run pytest
```

### Running Tests
```bash
# Run all tests (coverage included by default)
poetry run pytest

# Run tests with specific coverage reports
poetry run pytest --cov=app --cov-report=html --cov-report=xml --cov-report=json

# Run tests without coverage (if needed)
poetry run pytest --no-cov

# Run specific test file
poetry run pytest tests/test_filename.py

# Run integration tests
poetry run pytest -m integration

# Run async tests
poetry run pytest -m asyncio

# Watch mode - rerun tests on file changes (requires pytest-watch)
poetry run ptw

# Run tests in parallel (requires pytest-xdist)
poetry run pytest -n auto

# Run only tests that failed in the last run
poetry run pytest --lf

# Run tests with verbose output and show local variables on failure
poetry run pytest -vvl
```

### Coverage Analysis
```bash
# Generate comprehensive coverage report
bash scripts/coverage-report.sh

# Check coverage with ratcheting mechanism
bash scripts/coverage-check.sh

# View coverage report in browser
open htmlcov/index.html

# Display coverage summary
poetry run coverage report --show-missing --sort=Cover

# Generate coverage reports in different formats
poetry run coverage html    # HTML report
poetry run coverage xml     # XML report (for CI)
poetry run coverage json    # JSON report (for automation)
```

### Code Quality
```bash
# Type checking
poetry run mypy .

# Code formatting
poetry run black .

# Linting
poetry run ruff .

# Security scan
poetry run bandit -r app/

# Check unused code
poetry run vulture app/
```

### Development Setup
```bash
# Install dependencies
poetry install

# Start all services (uses consolidated Dockerfile with multi-stage builds)
docker-compose up -d

# Start specific service
docker-compose up -d app worker recorder reconciler

# View logs
docker-compose logs -f [service_name]

# Scale workers
docker-compose up -d --scale worker=3

# Run FastAPI server locally
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker Build Commands
```bash
# Build all services (uses multi-stage Dockerfile)
docker-compose build

# Build specific service target
docker build --target app -t pantry-pirate-radio:app .
docker build --target worker -t pantry-pirate-radio:worker .
docker build --target recorder -t pantry-pirate-radio:recorder .
docker build --target scraper -t pantry-pirate-radio:scraper .
docker build --target test -t pantry-pirate-radio:test .

# Run tests using Docker
docker build --target test -t pantry-pirate-radio:test .
docker run --rm pantry-pirate-radio:test
```

### Running Scrapers
```bash
# List available scrapers
python -m app.scraper --list

# Run specific scraper
python -m app.scraper nyc_efap_programs

# Run all scrapers
python -m app.scraper --all

# Run scrapers in parallel
python -m app.scraper --all --parallel --max-workers 4

# Test scrapers without processing
python -m app.scraper.test_scrapers --all
```

### CI Checks
```bash
# Run all expected CI checks
./scripts/run-ci-checks.sh
```

## Architecture Overview

## TDD Memories

### TDD Philosophy and Best Practices
- **TDD Rule**: Write a failing test before any production code - if you're tempted to code first, you're about to build the wrong thing. Tests aren't validation, they're specification: they force you to define exactly what success looks like before you get seduced by clever implementations that solve the wrong problem. Every line of untested code is a liability waiting to break in production, and every test written after the fact is just wishful thinking disguised as quality assurance. The red-green-refactor cycle isn't just methodology, it's discipline - it keeps you honest about what you're actually building versus what you think you're building. When you write tests first, you're not just preventing bugs, you're preventing entire categories of design mistakes that would otherwise plague your codebase for months.
- TDD Rule: Write a failing test before any production code - if you're tempted to code first, you're about to build the wrong thing.

### Commit Philosophy
- **Atomic Commits Rule**: Each commit must represent one complete, logical change that could stand alone - if you can't describe your commit in a single sentence without using "and", you're committing too much. Atomic commits aren't just good practice, they're your future self's lifeline: they make git bisect actually useful, code reviews focused and meaningful, and rollbacks surgical instead of catastrophic. When you bundle multiple changes into one commit, you're not saving time, you're creating archaeological puzzles for whoever has to debug your code later. The discipline of atomic commits forces you to think in discrete problem-solving steps rather than chaotic coding sessions, and each commit becomes a breadcrumb trail showing exactly how you solved each piece of the puzzle. Mixed commits are technical debt in disguise - they look efficient in the moment but cost exponentially more when you need to understand, revert, or cherry-pick changes months later.
- **Commit-As-You-Go TDD Rule**: Commit at every stage of the red-green-refactor cycle - failing test, passing implementation, and clean refactor each deserve their own atomic commit because your git history should tell the story of how you solved the problem, not just what the final solution looks like. Waiting until "everything is done" to commit is like writing a book and only saving it at the end - you're one power outage away from losing hours of thoughtful work. Each TDD phase commit creates a safety net: if your refactoring goes sideways, you can instantly return to working code; if your implementation gets too complex, you can restart from the clean failing test. The three-commit TDD rhythm creates a narrative that future developers (including yourself) can follow: "here's what they wanted to achieve, here's how they made it work, here's how they made it clean." When you commit continuously through TDD, you're not just saving your work, you're creating a masterclass in problem-solving that turns your git log into executable documentation of your thought process.