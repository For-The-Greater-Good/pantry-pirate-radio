# Feeding America Scraper Development Tracking System

This directory contains tools to help track and manage the development of scrapers for Feeding America food banks.

## Overview

We have 276 food banks that need scrapers. This tracking system helps:
- Track progress on each food bank scraper
- Identify high-priority targets (those with URLs)
- Generate boilerplate code from templates
- Update status as work progresses

## Scripts

### 1. `generate_scraper_tracking.py`

Generates a comprehensive tracking JSON file by fetching GitHub issues and cross-referencing with Feeding America data.

```bash
# Generate the tracking file
./generate_scraper_tracking.py

# Generate with report
./generate_scraper_tracking.py --report

# Filter by state
./generate_scraper_tracking.py --state CA

# Export to CSV
./generate_scraper_tracking.py --format csv

# Update existing tracking (preserves status)
./generate_scraper_tracking.py --update
```

### 2. `update_scraper_progress.py`

Updates task status as you work on scrapers.

```bash
# Show next priority tasks
./update_scraper_progress.py --next 10

# List all in-progress tasks
./update_scraper_progress.py --list-in-progress

# Mark scraper as in progress
./update_scraper_progress.py --issue 123 --task scraper --status in_progress

# Mark scraper as completed with file path
./update_scraper_progress.py --issue 123 --task scraper --status completed --file app/scraper/food_bank_name_scraper.py

# Add a note
./update_scraper_progress.py --issue 123 --note "Website uses React SPA, need browser automation"

# Mark PR as completed
./update_scraper_progress.py --issue 123 --task pr --status completed --pr 456
```

### 3. `extract_feeding_america_foodbanks.py`

Fetches food bank data from Feeding America API:
- Food bank names and organization IDs
- Addresses and contact information
- Website and food finder URLs
- Counties served
- State locations

### 4. `create_feeding_america_issues.py`

Creates GitHub issues for food banks that need scrapers.

### 5. `check_vivery_usage.py`

Detects which food banks use Vivery/AccessFood by checking their websites.

### 6. `close_vivery_issues.py`

Closes GitHub issues for food banks that are covered by the Vivery scraper.

## Templates

### Scraper Template (`/templates/scraper_template.py.jinja2`)

A Jinja2 template for generating scraper boilerplate. Variables:
- `food_bank_name`: Full name of the food bank
- `class_name`: PascalCase class name (e.g., "FoodBankOfAlaska")
- `scraper_id`: Snake_case scraper ID (e.g., "food_bank_of_alaska")
- `module_name`: Module name (e.g., "food_bank_of_alaska")
- `food_bank_url`: URL to scrape
- `state`: Two-letter state code

### Test Template (`/templates/test_scraper_template.py.jinja2`)

A Jinja2 template for generating test boilerplate with the same variables.

## Workflow

### 1. Find Next Task

```bash
# Show high-priority tasks (those with URLs)
./update_scraper_progress.py --next 10
```

### 2. Start Working on a Scraper

```bash
# Mark as in progress
./update_scraper_progress.py --issue 123 --task scraper --status in_progress

# Manually create scraper from template
# (Each site is unique, so manual exploration is needed)
```

### 3. Explore the Website

Each food bank website is unique. You'll need to:
1. Visit the food bank's URL
2. Explore how they present location data
3. Determine if they use:
   - Static HTML pages
   - JavaScript-rendered content
   - API endpoints
   - Third-party services (like Vivery)
4. Choose appropriate scraping approach

### 4. Implement the Scraper

Use the template as a starting point, but customize based on what you find:
- HTML parsing with BeautifulSoup
- API calls if endpoints are discovered
- Browser automation for JavaScript-heavy sites
- Geographic grid searches for API-based systems

### 5. Update Progress

```bash
# Mark scraper as completed
./update_scraper_progress.py --issue 123 --task scraper --status completed --file app/scraper/food_bank_name_scraper.py

# Add notes about implementation
./update_scraper_progress.py --issue 123 --note "Uses WordPress store locator plugin with AJAX endpoint"
```

### 6. Write Tests

```bash
# Mark tests as in progress
./update_scraper_progress.py --issue 123 --task tests --status in_progress

# After completion
./update_scraper_progress.py --issue 123 --task tests --status completed --file tests/test_scraper/test_food_bank_name_scraper.py
```

### 7. Submit PR

```bash
# After PR is created
./update_scraper_progress.py --issue 123 --task pr --status completed --pr 456
```

## Tracking Data Structure

The tracking JSON (`outputs/scraper_development_tracking.json`) contains:

```json
{
  "metadata": {
    "generated_at": "2025-01-27T...",
    "total_food_banks": 276,
    "completed": 0,
    "in_progress": 0,
    "pending": 276
  },
  "food_banks": [
    {
      "issue_number": 123,
      "issue_title": "Implement scraper for Food Bank Name",
      "food_bank": {
        "name": "Food Bank Name",
        "org_id": "123",
        "state": "CA",
        "url": "https://...",
        "find_food_url": "https://...",
        "counties": ["..."]
      },
      "tasks": {
        "scraper": {
          "status": "pending|in_progress|completed",
          "file_path": null,
          "completed_at": null
        },
        "tests": {
          "status": "pending|in_progress|completed",
          "file_path": null,
          "completed_at": null
        },
        "pr": {
          "status": "pending|in_progress|completed",
          "pr_number": null,
          "completed_at": null
        }
      },
      "priority": "high|medium|low",
      "assigned_to": null,
      "notes": []
    }
  ],
  "statistics": {
    "by_state": {},
    "by_priority": {},
    "completion_rate": {}
  }
}
```

## Priority System

- **High**: Food banks with `find_food_url` or `url` (easier to scrape)
- **Medium**: Food banks with state information
- **Low**: Others

## Important Notes

- Many food banks use Vivery (formerly PantryNet) for their food finders
- Always check for Vivery integration before implementing a custom scraper
- The Vivery API scraper (`app/scraper/vivery_api_scraper.py`) already covers these
- 31 food banks have been identified as Vivery users and their issues closed

## Statistics

As of the last run:
- Total food banks: 276
- High priority: 209 (have URLs)
- Medium priority: 67 (have state info)
- Low priority: 0

This means 75% of food banks have URLs we can explore!

## Tips

1. **Start with high-priority tasks** - they have URLs to explore
2. **Document findings** - use notes to record important details
3. **Check for existing patterns** - some food banks use similar systems
4. **Test thoroughly** - each scraper should handle edge cases
5. **Follow TDD** - write tests before implementation