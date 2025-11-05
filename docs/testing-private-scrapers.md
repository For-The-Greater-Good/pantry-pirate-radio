# Testing Private Scrapers in CI

This document explains how to set up and test private scrapers in the CI/CD pipeline.

## Overview

The project uses a hybrid architecture:
- **Public Framework**: Core scraper functionality in `app/scraper/` (utils, base classes, sample scraper)
- **Private Implementations**: Actual scrapers in `app/scraper/scrapers/` (private submodule)

CI automatically tests both when configured, but gracefully falls back to framework-only testing when private scrapers aren't available.

## Setup Instructions

### 1. Create GitHub Personal Access Token

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a descriptive name: "Pantry Pirate Radio CI Submodule Access"
4. Select scopes:
   - `repo` (Full control of private repositories)
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again)

### 2. Add Token as Repository Secret

1. Go to the main repository: `For-The-Greater-Good/pantry-pirate-radio`
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `SUBMODULE_TOKEN`
5. Value: Paste your personal access token
6. Click "Add secret"

### 3. Verify Setup

Once the token is added:
1. Push a commit to any branch
2. Check the GitHub Actions workflow
3. Look for the step "Checkout private scrapers submodule (if token available)"
4. It should output: "Token available, checking out private scrapers submodule..."
5. The pytest run should show tests for both framework and private scrapers

## How It Works

### CI Workflow

The CI pipeline conditionally checks out the private submodule:

```yaml
- name: Checkout private scrapers submodule (if token available)
  env:
    SUBMODULE_TOKEN: ${{ secrets.SUBMODULE_TOKEN }}
  run: |
    if [ -n "$SUBMODULE_TOKEN" ]; then
      echo "Token available, checking out private scrapers submodule..."
      git config --global url."https://${SUBMODULE_TOKEN}@github.com/".insteadOf "https://github.com/"
      git submodule update --init app/scraper/scrapers
      echo "Private scrapers submodule checked out successfully"
    else
      echo "No token available, skipping private scrapers submodule"
      echo "Tests will run against public framework only"
    fi
```

### Test Discovery

Tests in `tests/test_scraper/test_all_scrapers.py` dynamically discover scrapers:

- **Framework scrapers**: Listed by name (e.g., `sample`)
- **Private scrapers**: Namespaced with `scrapers.` prefix (e.g., `scrapers.foodfinder_us`)

The test suite:
1. Discovers all available scrapers using `list_available_scrapers()`
2. Tests each scraper can be loaded and instantiated
3. Verifies ScraperJob interface compliance
4. Validates naming conventions
5. Gracefully handles missing private scrapers

## Testing Locally

### With Private Scrapers

```bash
# Ensure submodule is initialized
git submodule update --init app/scraper/scrapers

# Run all scraper tests
./bouy test --pytest tests/test_scraper/

# Run specific scraper test
./bouy test --pytest tests/test_scraper/test_all_scrapers.py
```

### Without Private Scrapers

```bash
# Tests will automatically skip private scrapers
./bouy test --pytest tests/test_scraper/
```

## Test Output Examples

### With Private Scrapers Available

```
tests/test_scraper/test_all_scrapers.py::test_scrapers_discovered PASSED
tests/test_scraper/test_all_scrapers.py::test_framework_scrapers_present PASSED
tests/test_scraper/test_all_scrapers.py::test_private_scrapers_optional PASSED
  Found 30 private scrapers:
    - scrapers.foodfinder_us
    - scrapers.maryland_food_bank_md
    - scrapers.capital_area_food_bank_dc
    ...

tests/test_scraper/test_all_scrapers.py::test_scraper_can_be_loaded[sample] PASSED
tests/test_scraper/test_all_scrapers.py::test_scraper_can_be_loaded[scrapers.foodfinder_us] PASSED
...
```

### Without Private Scrapers

```
tests/test_scraper/test_all_scrapers.py::test_scrapers_discovered PASSED
tests/test_scraper/test_all_scrapers.py::test_framework_scrapers_present PASSED
tests/test_scraper/test_all_scrapers.py::test_private_scrapers_optional PASSED
  Found 0 private scrapers:
    (No private scrapers available - this is OK for CI without credentials)

tests/test_scraper/test_all_scrapers.py::test_scraper_can_be_loaded[sample] PASSED
```

## Open Source Contributors

Open source contributors **do not** need access to private scrapers:

- CI will run successfully testing only the public framework
- All framework tests pass without the submodule
- Contributors can develop custom scrapers using the public API
- No setup required - just clone and test

## Security Considerations

- The `SUBMODULE_TOKEN` secret is never exposed in logs
- Token has minimal required scope (`repo` only)
- Token can be rotated if compromised
- Falls back gracefully if token is missing or invalid

## Troubleshooting

### CI shows "No token available"

**Cause**: SUBMODULE_TOKEN secret not configured

**Solution**: Follow setup instructions above to add the secret

### Tests fail with "No module named 'scrapers'"

**Cause**: Private submodule not checked out but tests expect it

**Solution**:
- Locally: `git submodule update --init app/scraper/scrapers`
- In CI: Verify SUBMODULE_TOKEN secret is correctly configured

### Token authentication failed

**Cause**: Invalid or expired token

**Solution**:
1. Generate new personal access token
2. Update SUBMODULE_TOKEN secret with new value

## Related Documentation

- [Scraper Patterns](./scraper-patterns.md) - How to create custom scrapers
- [CI/CD Pipeline](../GITHUB_WORKFLOWS.md) - Complete CI workflow documentation
- [Architecture](./architecture.md) - System architecture overview
