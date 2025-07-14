# Feeding America Food Bank Issue Generation

This directory contains scripts for generating GitHub issues for all Feeding America food banks.

## Data Source

The food bank data is extracted from:
**https://www.feedingamerica.org/find-your-local-foodbank/all-food-banks**

This page lists all 198 Feeding America member food banks across the United States.

## How to Use

### 1. Get the Food Bank Data

Save the HTML content from the Feeding America page:
```bash
# Option 1: Using curl
curl -o feeding-america-foodbanks.html "https://www.feedingamerica.org/find-your-local-foodbank/all-food-banks"

# Option 2: Save the page manually from your browser
# File -> Save Page As -> feeding-america-foodbanks.html
```

### 2. Extract Food Bank Information

```bash
# Extract data from the HTML file (run from project root)
poetry run python scripts/feeding-america/extract_feeding_america_foodbanks.py feeding-america-foodbanks.html

# This creates:
# - outputs/feeding_america_foodbanks.json (raw data)
# - outputs/feeding_america_issues.json (GitHub issue templates)
# - outputs/feeding_america_summary.md (summary report)
```

### 3. Create GitHub Issues

```bash
# Test with dry run first
poetry run python scripts/feeding-america/create_feeding_america_issues.py --dry-run --limit 5

# Create issues in batches
poetry run python scripts/feeding-america/create_feeding_america_issues.py --limit 10 --yes

# Create issues for specific state
poetry run python scripts/feeding-america/create_feeding_america_issues.py --state CA --limit 5 --yes
```

## Scripts

### extract_feeding_america_foodbanks.py
Parses the HTML from Feeding America's website and extracts:
- Food bank names and organization IDs
- Addresses and contact information
- Website and food finder URLs
- Counties served
- State locations

The script also identifies potential Vivery users based on URL patterns.

### create_feeding_america_issues.py
Creates GitHub issues with comprehensive implementation instructions including:
- Food bank details
- Vivery detection instructions
- Code templates
- Documentation references
- Testing commands

## Important Notes

- Many food banks use Vivery (formerly PantryNet) for their food finders
- Always check for Vivery integration before implementing a custom scraper
- The Vivery API scraper (`app/scraper/vivery_api_scraper.py`) already covers these
- Each issue includes instructions for checking Vivery

## Output Files

After running the extraction script, you'll find:
- `outputs/feeding_america_foodbanks.json` - Complete food bank data
- `outputs/feeding_america_issues.json` - GitHub issue templates
- `outputs/feeding_america_summary.md` - Summary by state
- `outputs/vivery_candidates.json` - Potential Vivery users

## Issue Labels

Each issue is created with:
- `scraper` - Indicates a scraper implementation task
- `food-bank` - Specific to food bank scrapers
- `help wanted` - Open for contribution