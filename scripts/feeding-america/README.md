# Feeding America Scraper Development Tracking System

This directory contains tools to help track and manage the development of scrapers for Feeding America food banks.

## Overview

We have 276 food banks that need scrapers. This tracking system provides a comprehensive suite of tools to:
- Extract food bank data from the Feeding America API
- Track scraper development progress across GitHub issues
- Identify and handle Vivery/AccessFood-powered sites
- Generate boilerplate code from templates
- Prioritize tasks based on population served
- Automate scraper implementation with AI assistance
- Update status as work progresses

## Prerequisites

- Docker (all commands run through bouy)
- GitHub CLI (`gh`) configured with repository access
- Network access to Feeding America API and food bank websites

## Scripts

### 1. `extract_feeding_america_foodbanks.py`

Fetches comprehensive food bank data directly from the Feeding America API. This is the foundation script that gathers all food bank information.

**Purpose**: Extract and structure food bank data including names, addresses, URLs, service areas, and contact information.

**Usage**:
```bash
# Fetch all food bank data from API
./bouy exec app python scripts/feeding-america/extract_feeding_america_foodbanks.py

# With custom output file
./bouy exec app python scripts/feeding-america/extract_feeding_america_foodbanks.py --output custom.json

# Include affiliate organizations
./bouy exec app python scripts/feeding-america/extract_feeding_america_foodbanks.py --include-affiliates
```

**Output**: Creates `outputs/feeding_america_foodbanks.json` containing:
- Organization IDs and names
- Physical and mailing addresses with coordinates
- Website URLs and food finder URLs
- Service areas (counties)
- Social media links
- Logo URLs
- Affiliate relationships

### 2. `generate_scraper_tracking.py`

Generates a comprehensive tracking JSON file by fetching GitHub issues and cross-referencing with Feeding America data. This is the central tracking system for all scraper development.

**Purpose**: Create and maintain a master tracking file that combines GitHub issues with food bank metadata.

**Usage**:
```bash
# Generate the tracking file
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py

# Generate with detailed report
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py --report

# Filter by state
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py --state CA

# Export to CSV format
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py --format csv

# Update existing tracking (preserves task status)
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py --update
```

**Output**: Creates `outputs/scraper_development_tracking.json` with task status for each food bank

### 3. `update_scraper_progress.py`

Updates task status as you work on scrapers. This is the primary tool for tracking your progress through the development workflow.

**Purpose**: Manage task states (pending/in_progress/completed) and track implementation details.

**Usage**:
```bash
# Show next priority tasks
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --next 10

# List all in-progress tasks
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --list-in-progress

# Mark scraper as in progress
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task scraper --status in_progress

# Mark scraper as completed with file path
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task scraper --status completed --file app/scraper/food_bank_name_scraper.py

# Add implementation notes
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --note "Website uses React SPA, need browser automation"

# Mark PR as completed
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task pr --status completed --pr 456

# Show summary statistics
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --summary
```

**Task Types**:
- `scraper`: The main implementation file
- `tests`: Unit tests for the scraper
- `pr`: Pull request submission

### 4. `create_feeding_america_issues.py`

Creates GitHub issues for food banks that need scrapers. Uses the GitHub CLI to batch-create issues with proper labels and formatting.

**Purpose**: Automate GitHub issue creation for tracking scraper implementation tasks.

**Usage**:
```bash
# Create 5 issues (default)
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py

# Create specific number of issues
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --limit 10

# Start from a specific index
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --start 50 --limit 10

# Filter by state
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --state NY --limit 5

# Exclude Vivery-powered sites
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --exclude-vivery

# Dry run (preview without creating)
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --dry-run --limit 10

# Skip confirmation prompt
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --yes --limit 5

# Custom delay between API calls
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --delay 3
```

**Required**: GitHub CLI must be authenticated (`gh auth status`)

### 5. `check_vivery_usage.py`

Detects which food banks use Vivery/AccessFood/PantryNet by analyzing their websites. This helps identify sites that don't need custom scrapers.

**Purpose**: Automatically detect Vivery-powered sites to avoid duplicate scraper development.

**Usage**:
```bash
# Check all food banks for Vivery usage
./bouy exec app python scripts/feeding-america/check_vivery_usage.py

# Check specific state
./bouy exec app python scripts/feeding-america/check_vivery_usage.py --state CA

# Custom timeout for slow sites
./bouy exec app python scripts/feeding-america/check_vivery_usage.py --timeout 15

# Skip SSL verification (for testing)
./bouy exec app python scripts/feeding-america/check_vivery_usage.py --no-verify-ssl
```

**Detection Methods**:
- AccessFood widget divs and data attributes
- CDN resources from food-access-widget-cdn.azureedge.net
- Iframes from pantrynet.org, vivery.com, or accessfood.org
- "Powered by" text mentions
- Script includes and API references
- Vivery-specific CSS classes and IDs

**Output**:
- `outputs/vivery_confirmed_users.json`: Food banks confirmed to use Vivery
- `outputs/vivery_check_summary.json`: Summary statistics

### 6. `close_vivery_issues.py`

Closes GitHub issues for food banks that are covered by the existing Vivery API scraper.

**Purpose**: Automatically close issues for Vivery-powered sites with appropriate comments.

**Usage**:
```bash
# Dry run to preview what would be closed
./bouy exec app python scripts/feeding-america/close_vivery_issues.py --dry-run

# Actually close the issues
./bouy exec app python scripts/feeding-america/close_vivery_issues.py

# Custom delay between API calls
./bouy exec app python scripts/feeding-america/close_vivery_issues.py --delay 2
```

**Process**:
1. Loads confirmed Vivery users from `check_vivery_usage.py` output
2. Searches for matching GitHub issues
3. Adds comment: "Covered by vivery_api_scraper.py"
4. Closes the issue

**Output**: `outputs/vivery_issues_closed.json` with closure results

### 7. `create_scraper_from_issue.py`

Generates scraper boilerplate code from a GitHub issue using Jinja2 templates.

**Purpose**: Quickly scaffold new scraper files with proper structure and naming.

**Usage**:
```bash
# Create scraper files for a specific issue
./bouy exec app python scripts/feeding-america/create_scraper_from_issue.py --issue 123

# Dry run to preview file creation
./bouy exec app python scripts/feeding-america/create_scraper_from_issue.py --issue 123 --dry-run
```

**Generated Files**:
- `app/scraper/{module_name}_scraper.py`: Main scraper implementation
- `tests/test_scraper/test_{module_name}_scraper.py`: Test file

**Features**:
- Automatically sanitizes food bank names for Python identifiers
- Includes state in naming for uniqueness
- Adds approximate state coordinates for geocoding
- Updates tracking to mark scraper as "in_progress"
- Provides next steps and implementation guidance

### 8. `pick_next_scraper_task.py`

Intelligently selects the next scraper task to work on based on priority and randomization.

**Purpose**: Help developers choose which scraper to implement next using priority-weighted selection.

**Usage**:
```bash
# Pick a random task and show implementation instructions
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py

# List available tasks instead of picking one
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py --list

# Only select from top priority tasks
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py --top-priority

# Filter by specific priority level
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py --priority HIGH

# Show more pending tasks
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py --list --limit 20
```

**Selection Algorithm**:
- CRITICAL priority: Always selected first if available
- Weighted random selection based on priority levels
- Provides complete implementation instructions
- Shows all necessary commands and file paths

### 9. `prioritize_scraper_issues.py`

Analyzes and updates GitHub issue titles with priority levels based on population served.

**Purpose**: Assign priority levels to scraper tasks based on metropolitan area populations.

**Usage**:
```bash
# Analyze and show priority distribution
./bouy exec app python scripts/feeding-america/prioritize_scraper_issues.py --stats-only

# Update issue titles with priorities (dry run)
./bouy exec app python scripts/feeding-america/prioritize_scraper_issues.py --dry-run

# Actually update GitHub issue titles
./bouy exec app python scripts/feeding-america/prioritize_scraper_issues.py

# Custom delay between API calls
./bouy exec app python scripts/feeding-america/prioritize_scraper_issues.py --delay 2
```

**Priority Levels**:
- **CRITICAL**: Major metros with 5M+ population (NYC, LA, Chicago, etc.)
- **HIGH**: Large cities with 1-5M population
- **MEDIUM**: Mid-size cities with 500K-1M population
- **LOW**: Smaller areas under 500K population

### 10. `implement_scraper_with_claude.py`

Generates comprehensive prompts for Claude to implement scrapers with full context.

**Purpose**: Automate scraper implementation by providing Claude with all necessary information.

**Usage**:
```bash
# Generate prompt for a random pending scraper
./bouy exec app python scripts/feeding-america/implement_scraper_with_claude.py

# Generate for a specific issue
./bouy exec app python scripts/feeding-america/implement_scraper_with_claude.py --issue 123

# Filter by priority
./bouy exec app python scripts/feeding-america/implement_scraper_with_claude.py --priority CRITICAL

# Copy prompt to clipboard (macOS)
./bouy exec app python scripts/feeding-america/implement_scraper_with_claude.py | pbcopy
```

**Generated Context**:
- Food bank details and URLs
- Example scraper code
- Test requirements
- File paths and naming conventions
- Implementation guidelines

### 11. `test_priority_system.py`

Tests and validates the priority-based task selection system.

**Purpose**: Verify that the priority system is working correctly.

**Usage**:
```bash
# Run all priority system tests
./bouy exec app python scripts/feeding-america/test_priority_system.py
```

**Tests**:
- Priority statistics validation
- Task list grouping verification
- Selection algorithm testing
- Priority filtering checks

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

### Initial Setup

```bash
# 1. Extract food bank data from API
./bouy exec app python scripts/feeding-america/extract_feeding_america_foodbanks.py

# 2. Generate tracking file
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py

# 3. Check for Vivery usage
./bouy exec app python scripts/feeding-america/check_vivery_usage.py

# 4. Close Vivery-covered issues
./bouy exec app python scripts/feeding-america/close_vivery_issues.py --dry-run

# 5. Prioritize remaining issues
./bouy exec app python scripts/feeding-america/prioritize_scraper_issues.py
```

### Development Workflow

#### 1. Find Next Task

```bash
# Pick a random high-priority task
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py

# Or show list of available tasks
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --next 10
```

#### 2. Start Working on a Scraper

```bash
# Generate boilerplate files from template
./bouy exec app python scripts/feeding-america/create_scraper_from_issue.py --issue 123

# This automatically marks the task as in_progress
# Or manually update status:
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task scraper --status in_progress
```

#### 3. Explore the Website

Each food bank website is unique. You'll need to:
1. Visit the food bank's URL
2. Explore how they present location data
3. Determine if they use:
   - Static HTML pages
   - JavaScript-rendered content
   - API endpoints
   - Third-party services (like Vivery)
4. Choose appropriate scraping approach

#### 4. Implement the Scraper

Use the template as a starting point, but customize based on what you find:
- HTML parsing with BeautifulSoup
- API calls if endpoints are discovered
- Browser automation for JavaScript-heavy sites
- Geographic grid searches for API-based systems

#### 5. Update Progress

```bash
# Mark scraper as completed
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task scraper --status completed --file app/scraper/food_bank_name_scraper.py

# Add notes about implementation
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --note "Uses WordPress store locator plugin with AJAX endpoint"
```

#### 6. Write Tests

```bash
# Mark tests as in progress
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task tests --status in_progress

# Run the tests
./bouy test --pytest tests/test_scraper/test_food_bank_name_scraper.py

# After completion
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task tests --status completed --file tests/test_scraper/test_food_bank_name_scraper.py
```

#### 7. Submit PR

```bash
# Create pull request
git add app/scraper/food_bank_name_scraper.py tests/test_scraper/test_food_bank_name_scraper.py
git commit -m "feat: Add scraper for Food Bank Name"
git push origin feature/food-bank-name-scraper
gh pr create --title "Add scraper for Food Bank Name" --body "Closes #123"

# Update tracking with PR number
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task pr --status completed --pr 456
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

## Environment Variables

No special environment variables are required. The scripts use:
- GitHub CLI (`gh`) for API access - must be authenticated
- Standard Python libraries (no additional pip installs needed)
- Network access for fetching web pages and APIs

## Data Files

All scripts work with JSON files in the `outputs/` directory:

| File | Description | Generated By |
|------|-------------|-------------|
| `feeding_america_foodbanks.json` | Raw food bank data from API | `extract_feeding_america_foodbanks.py` |
| `feeding_america_issues.json` | Formatted GitHub issues | `create_feeding_america_issues.py` |
| `scraper_development_tracking.json` | Master tracking file | `generate_scraper_tracking.py` |
| `vivery_confirmed_users.json` | Vivery-powered sites | `check_vivery_usage.py` |
| `vivery_check_summary.json` | Vivery detection summary | `check_vivery_usage.py` |
| `vivery_issues_closed.json` | Closed issue records | `close_vivery_issues.py` |

## Troubleshooting

### Common Issues and Solutions

#### GitHub CLI Authentication
```bash
# Check if gh is authenticated
gh auth status

# If not authenticated, login
gh auth login
```

#### Missing Tracking File
```bash
# Regenerate tracking file
./bouy exec app python scripts/feeding-america/generate_scraper_tracking.py
```

#### SSL Certificate Errors
```bash
# For check_vivery_usage.py, SSL verification is already disabled
# The script handles this automatically
```

#### Rate Limiting
```bash
# Increase delay between API calls
./bouy exec app python scripts/feeding-america/create_feeding_america_issues.py --delay 5
```

#### Script Permissions
```bash
# Scripts are run through bouy, so no chmod needed
# Always use: ./bouy exec app python scripts/feeding-america/script_name.py
```

## Important Notes

- Many food banks use Vivery (formerly PantryNet/AccessFood) for their food finders
- Always check for Vivery integration before implementing a custom scraper
- The Vivery API scraper (`app/scraper/vivery_api_scraper.py`) already covers these
- 31+ food banks have been identified as Vivery users and their issues closed
- Use bouy commands for all script execution to ensure proper environment

## Statistics

As of the last run:
- Total food banks: 276
- High priority: 209 (have URLs)
- Medium priority: 67 (have state info)
- Low priority: 0

This means 75% of food banks have URLs we can explore!

## Best Practices

1. **Start with high-priority tasks** - they serve larger populations
2. **Check for Vivery first** - avoid duplicate work on already-covered sites
3. **Document findings** - use notes to record implementation details
4. **Check for existing patterns** - some food banks use similar systems:
   - WordPress store locators
   - Squarespace integrations
   - Custom React SPAs
   - Google Maps integrations
5. **Test thoroughly** - each scraper should handle:
   - Missing data gracefully
   - Network timeouts
   - Rate limiting
   - Data validation
6. **Follow TDD** - write tests before implementation
7. **Use templates** - start from boilerplate to maintain consistency
8. **Update tracking regularly** - helps team coordination

## Quick Reference

```bash
# Complete workflow for implementing a new scraper
# 1. Pick a task
./bouy exec app python scripts/feeding-america/pick_next_scraper_task.py

# 2. Create boilerplate (replace 123 with actual issue number)
./bouy exec app python scripts/feeding-america/create_scraper_from_issue.py --issue 123

# 3. Implement the scraper
# (Edit app/scraper/food_bank_name_scraper.py)

# 4. Test the scraper
./bouy scraper-test food_bank_name
./bouy test --pytest tests/test_scraper/test_food_bank_name_scraper.py

# 5. Update tracking
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task scraper --status completed
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task tests --status completed

# 6. Submit PR and update
./bouy exec app python scripts/feeding-america/update_scraper_progress.py --issue 123 --task pr --status completed --pr 456
```