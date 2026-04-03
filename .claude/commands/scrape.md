---
description: Interactive workflow to generate a new food bank scraper from a GitHub issue
---

## User Input
```text
$ARGUMENTS
```

## Workflow Overview

This command guides you through creating a new food bank scraper:
1. **Issue Selection** - Pick next priority task or specify issue number
2. **Vivery Detection** - Check if site is already covered (critical deduplication)
3. **Website Analysis** - Analyze structure and suggest approach
4. **Code Generation** - Create scraper and test files from templates
5. **Testing & Execution** - Run tests and execute scraper to verify it works

## Execution Steps

### Step 1: Parse Arguments and Select Issue

**Parse `$ARGUMENTS`:**
- If empty or "next": Use priority-based selection
- If numeric: Treat as GitHub issue number
- Otherwise: Error with usage instructions

**If "next" mode:**
1. Run the priority picker:
   ```bash
   ./bouy exec app python3 scripts/feeding-america/pick_next_scraper_task.py
   ```
2. Parse the output to extract:
   - Issue number
   - Food bank name
   - Priority level
   - State
   - URL
3. Ask user to confirm this is the issue they want to work on

**If issue number specified:**
1. Fetch issue details using GitHub CLI:
   ```bash
   gh issue view $ISSUE_NUMBER --json number,title,body,labels,state
   ```
2. Validate:
   - Issue exists
   - Has `scraper` label
   - Not already `completed` or `vivery-covered`
   - Not currently `in-progress` (warn but allow override)
3. Parse issue body to extract:
   - **Food Bank Name:** (from title or body)
   - **State:** (from title or body)
   - **URL:** (from body)
   - **Counties Served:** (from body)
   - **Population Served:** (from body, for context)

**Display to user:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Selected Issue #123: [HIGH] Food Bank of Example (CA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name:       Food Bank of Example
State:      California (CA)
URL:        https://example.org
Counties:   Example County, Demo County
Population: 1.2M
Priority:   HIGH
Labels:     scraper, feeding-america
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 2: Vivery Detection (CRITICAL - Must Not Skip)

**IMPORTANT:** Vivery/AccessFood sites are already covered by the `vivery_api_scraper.py`. We must check for Vivery **before** doing any work.

1. Check if the URL is accessible:
   ```bash
   curl -I --silent --head --location $URL | head -n 1
   ```
2. Run Vivery detection on the URL:
   ```bash
   ./bouy exec app python3 scripts/feeding-america/check_vivery_usage.py
   ```
   Note: This script accepts URLs via stdin or can check all from the JSON file

3. Alternative: Use browser tools to check directly:
   - Navigate to URL: `mcp__playwright__browser_navigate`
   - Take snapshot: `mcp__playwright__browser_snapshot`
   - Look for Vivery indicators:
     - `<div class="food-access-widget">` or `<div id="food-access-widget">`
     - Scripts from `food-access-widget-cdn.azureedge.net`
     - `window.AccessFood` or `window.ViveryWidget`
     - Any mention of "AccessFood" or "Vivery" in source

**If Vivery detected:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  VIVERY DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This site uses Vivery/AccessFood and is already covered
by the vivery_api_scraper.py in our system.

Building a custom scraper for this site would be:
• Duplicate work
• Less reliable (Vivery data is canonical)
• Waste of development time

Recommended action: Close this issue
```

Ask user:
- **A) Close issue and mark as vivery-covered (recommended)**
- **B) Proceed anyway (advanced - only if you have specific reason)**
- **C) Cancel and pick different issue**

If user chooses A:
1. Run: `./bouy exec app python3 scripts/feeding-america/close_vivery_issues.py --issue $ISSUE_NUMBER`
2. Display confirmation and stop workflow
3. Suggest running `/scrape next` to pick a different task

If user chooses B:
- Warn that this is not recommended
- Continue to next step

If user chooses C:
- Exit workflow
- Suggest running `/scrape next` or `/scrape [different-issue-number]`

**IMPORTANT: Dynamic Vivery Detection**
The HTML-based check (`check_vivery_usage.py`) can miss Vivery widgets that load dynamically via JavaScript. If the HTML check says "not detected", also verify by:
1. Opening the Find Food URL in a browser
2. Checking the rendered page for "AccessFood" or "Vivery" branding
3. Checking browser DevTools Network tab for requests to `api.accessfood.org`
4. Running in browser console: `document.querySelector('.accessfood-widget') || document.querySelector('[data-map]')`

East Texas Food Bank (#303) was missed by the initial HTML scan because its widget loaded dynamically.

**If Vivery NOT detected (both HTML and browser check):**
```
✓ Vivery check: Not detected (HTML + browser verified)
✓ This site requires a custom scraper
✓ Proceeding to analysis...
```

### Step 3: Website Analysis & Similar Scraper Discovery

**A) Automated Website Analysis**

Use browser tools to analyze the target website:

1. Navigate to the URL:
   ```
   mcp__playwright__browser_navigate(url: $URL)
   ```

2. Capture page snapshot:
   ```
   mcp__playwright__browser_snapshot()
   ```

3. Analyze the page structure and identify:
   - **Page Type:**
     - Static HTML (content in initial HTML)
     - React/Vue SPA (mostly `<div id="root">`)
     - WordPress (indicators: `wp-content`, `wp-includes`)
     - Squarespace/Wix (indicators in meta tags)

   - **Data Location:**
     - HTML tables (`<table>` with location data)
     - Div/List structure (`<div class="location">` or `<ul class="locations">`)
     - Map markers (JavaScript-based map with data)
     - PDF/downloadable list (link to PDF)
     - External widget/iframe

   - **JavaScript Requirements:**
     - Can data be scraped without JS? (view page source)
     - Does page require JavaScript to render locations?
     - Are there API calls visible in network tab?

4. If possible, identify potential selectors:
   - CSS selectors for location containers
   - Class names or IDs for location elements
   - Structure of address/phone/hours data

**B) Find Similar Scrapers**

Search for existing scrapers with similar patterns:

1. List all scrapers:
   ```bash
   ls -1 app/scraper/scrapers/*_scraper.py
   ```

2. Search for common patterns in existing scrapers:
   ```
   grep -l "BeautifulSoup" app/scraper/scrapers/*.py  # HTML parsing
   grep -l "httpx.*json" app/scraper/scrapers/*.py    # API calls
   grep -l "playwright" app/scraper/scrapers/*.py     # Browser automation
   ```

3. Read 2-3 similar scrapers as reference examples:
   - If HTML table detected → Look for scrapers with table parsing
   - If API detected → Look for API-based scrapers
   - If JS-heavy → Look for playwright-based scrapers

**C) Display Analysis to User**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 Website Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Page Type:     Static HTML
Data Location: HTML table with class "locations-table"
JS Required:   No - data in initial HTML
Structure:     15 rows, columns: name, address, phone, hours

Suggested CSS Selectors:
  table.locations-table tr
  td.location-name
  td.location-address

Similar Scrapers Found:
  1. food_bank_of_alaska_ak_scraper.py (HTML table)
  2. food_bank_of_iowa_ia_scraper.py (HTML divs)

Recommended Approach: HTML Parsing with BeautifulSoup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 4: Interactive Approach Selection

Ask the user to confirm approach using AskUserQuestion tool:

**Question 1: Scraping Approach**

**IMPORTANT: Always try approaches in this order:**
1. **Simple HTML Parsing** (BeautifulSoup) - Try first, fastest and most reliable
2. **API Investigation** - Look for JSON endpoints in network tab
3. **Browser Automation** (Playwright) - Only if above methods fail

```
Based on the website analysis, which approach should we use?

A) HTML Parsing (BeautifulSoup)
   - Best for: Static HTML with data in source
   - Fast and reliable
   - TRY THIS FIRST

B) API Endpoint
   - Best for: Sites with JSON APIs
   - Check network tab for API calls
   - Most reliable when available

C) Browser Automation (Playwright)
   - Best for: JavaScript-heavy sites
   - Slower but handles dynamic content
   - USE ONLY WHEN HTML/API FAILS

D) Hybrid Approach
   - Combination of above methods
   - For complex sites with multiple data sources
```

**Question 2: Implementation Scope**
```
How comprehensive should the scraper be?

A) Basic (Name, Address, Phone)
   - Minimum required fields
   - Fastest to implement
   - Good for quick wins

B) Standard (+ Hours, Services, Notes)
   - Include common optional fields
   - Better data quality
   - Recommended for most scrapers

C) Comprehensive (All available data)
   - Extract every field found
   - Maximum value but more work
   - Use for high-priority sites
```

Parse user responses and store for code generation.

### Step 5: Code Generation

**A) Run Existing Template Generator**

The `create_scraper_from_issue.py` script already handles:
- Fetching issue details from GitHub
- Parsing food bank info
- Generating unique filenames with state suffix
- Creating scraper and test files from Jinja2 templates
- Adding `in-progress` label to GitHub issue

Run the script:
```bash
./bouy exec app python3 scripts/feeding-america/create_scraper_from_issue.py $ISSUE_NUMBER
```

Parse the output to get:
- Scraper file path: `app/scraper/scrapers/{name}_scraper.py`
- Test file path: `app/scraper/scrapers/tests/test_{name}_scraper.py`

**B) Read Generated Files**

Use the Read tool to load both generated files:
- `app/scraper/scrapers/{name}_scraper.py`
- `app/scraper/scrapers/tests/test_{name}_scraper.py`

**IMPORTANT: All scrapers and tests must exist in the scrapers submodule:**
- Scraper location: `app/scraper/scrapers/{name}_scraper.py`
- Test location: `app/scraper/scrapers/tests/test_{name}_scraper.py`

**C) Enhance Generated Code**

Based on website analysis and user selections, suggest enhancements:

If **HTML Parsing** selected:
- Add specific CSS selectors discovered in analysis
- Include example HTML structure in comments
- Suggest BeautifulSoup methods (find_all, select, etc.)
- Show how to extract each field

If **API Endpoint** selected:
- Provide template for httpx requests
- Show JSON parsing structure
- Include error handling for API failures
- Add rate limiting if needed

If **Browser Automation** selected:
- Import playwright utilities
- Add wait conditions for dynamic content
- Include screenshot on failure for debugging
- Add explicit waits for elements

**D) Display Suggestions**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✏️  Files Generated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scraper: app/scraper/scrapers/food_bank_of_example_ca_scraper.py
Test:    app/scraper/scrapers/tests/test_food_bank_of_example_ca_scraper.py

✓ GitHub issue #123 marked as 'in-progress'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Suggested Enhancements:

1. Replace the TODO in scrape() method with:
   ```python
   response = httpx.get("https://example.org/locations")
   soup = BeautifulSoup(response.content, "html.parser")

   for row in soup.select("table.locations-table tr"):
       name = row.select_one("td.location-name").text.strip()
       address = row.select_one("td.location-address").text.strip()
       # ... extract other fields
   ```

2. Add error handling for missing fields
3. Validate addresses before creating Location objects

Would you like me to apply these enhancements automatically?
```

If user says yes, use the Edit tool to update the scraper file with suggestions.
If user says no, continue to testing phase.

### Step 6: Testing & Execution

**A) Run Unit Tests**

Execute the generated test file:
```bash
./bouy exec app pytest app/scraper/scrapers/tests/test_{name}_scraper.py -v
```

Display test results and offer to help fix failures if any.

**B) Run Full Scraper Execution**

Execute the scraper for real (commits to database):
```bash
./bouy scraper {scraper_name}
```

Parse output for:
- Number of locations found
- Any errors or warnings
- Sample location data

Display results:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Scraper Execution Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status:    ✓ Success
Locations: 15 found and saved to database
Sample:
  - Example Food Pantry
    123 Main St, Example, CA 90210
    (555) 123-4567

Warnings: None
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**C) Update GitHub Issue**

Add a comment to the GitHub issue documenting completion:
```bash
gh issue comment $ISSUE_NUMBER --body "Scraper implemented and tested successfully. Found {location_count} locations."
```

### Step 7: Summary & Next Steps

Display final summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Scraper Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 Files Created:
   app/scraper/scrapers/food_bank_of_example_ca_scraper.py
   app/scraper/scrapers/tests/test_food_bank_of_example_ca_scraper.py

📊 Results:
   Locations Found: 15
   Test Status: ✓ Passed
   Execution Status: ✓ Success

🚀 Ready to Submit:

   # Create PR and link to issue
   gh pr create --title "Add Food Bank of Example (CA) scraper" \
                --body "Implements scraper for issue #$ISSUE_NUMBER

   Scraper successfully finds {location_count} locations.

   Closes #$ISSUE_NUMBER"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Important Guidelines

### Vivery Detection is CRITICAL
- **NEVER skip the Vivery check** - it's the first rule of scraper generation
- Vivery sites are already covered by `vivery_api_scraper.py`
- Building duplicate scrapers wastes time and creates maintenance burden
- The check takes seconds, saves hours

### DO NOT Include Geocoding Logic
- **IMPORTANT:** Scrapers should NOT geocode addresses
- The validator service handles all geocoding automatically
- Only extract raw address text from the website
- Let the validator service convert addresses to coordinates
- This ensures:
  - Consistent geocoding across all scrapers
  - Centralized rate limiting and caching
  - Easier maintenance and improvements
  - Better error handling and fallback strategies

### Test Before Committing
- **IMPORTANT:** Use `./bouy exec app pytest` for testing scrapers, NOT `./bouy test`
- Always run `./bouy exec app pytest app/scraper/scrapers/tests/test_{name}_scraper.py` on the specific test file
- Always run `./bouy scraper {name}` for full execution and validation
- Fix syntax errors before moving to implementation
- Validate that locations are being extracted correctly

### Scraper Development Approach Priority
1. **Try Simple HTML Parsing First** - Use BeautifulSoup, fastest and most reliable
2. **Investigate API Endpoints** - Check network tab for JSON APIs
3. **Use Browser Automation Last** - Playwright only when HTML/API methods fail

### Use the Scraper Pattern Catalog
Before writing any scraper, read `app/scraper/scrapers/docs/scraper-patterns.md`. It contains:
- A decision tree for picking the right approach based on what you see on the website
- Detection commands to identify which WordPress plugin or data source is in use
- Reference scrapers for each pattern with field mappings
- Common pitfalls and implementation notes

**Pattern quick reference (most common first):**
- **Store Locator Plus (SLP):** `treasure_coast_food_bank_fl_scraper.py` (REST), `food_bank_of_north_alabama_al_scraper.py` (AJAX)
- **WP Store Locator (WPSL):** `forgotten_harvest_mi_scraper.py` (grid), `good_shepherd_food_bank_me_scraper.py`
- **Agile Store Locator (ASL):** `fulfill_nj_scraper.py`
- **Google My Maps KML:** `inter_faith_food_shuttle_nc_scraper.py`, `food_bank_for_new_york_city_ny_scraper.py`
- **Google Sheets JSON:** `food_bank_of_iowa_ia_scraper.py`
- **Simple JSON API:** `second_harvest_nw_nc_scraper.py`, `food_oasis_la_scraper.py`
- **ArcGIS FeatureServer:** `capital_area_food_bank_dc_scraper.py`

### GitHub Issue Management
- The `create_scraper_from_issue.py` script automatically adds `in-progress` label
- Use `update_scraper_progress.py` to update status
- Link PR number to issue when creating PR
- Mark as completed only after PR merges

## Error Handling

### If Issue Not Found
```
❌ Error: Issue #{number} not found

Make sure:
• Issue number is correct
• You have access to the repository
• GitHub CLI is authenticated: gh auth status

Try: /scrape next (to pick next priority task)
```

### If Services Not Running
```
❌ Error: Bouy services not running

Please start services first:
  ./bouy up

Then try again: /scrape {args}
```

### If Vivery Detection Fails
```
⚠️  Warning: Could not verify Vivery status

This might mean:
• Website is down or unreachable
• Network connectivity issues
• Script error

Recommended: Manual verification
Visit {url} and check for Vivery/AccessFood widgets

Continue anyway? (yes/no)
```

### If Script Execution Fails
```
❌ Error: Failed to execute {script_name}

Error output:
{error_message}

Troubleshooting:
• Check that services are running: ./bouy ps
• Check logs: ./bouy logs app
• Verify script exists: ls scripts/feeding-america/

Need help? Check logs or ask for assistance.
```

## Examples

### Example 1: Pick Next Priority Task
```
User: /scrape next

Output:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Priority-Based Selection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Selected Issue #156: [HIGH] Food Bank For New York City (NY)
Population Served: 1.5M
Priority: HIGH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Proceed with this issue? (yes/no)
```

### Example 2: Specific Issue Number
```
User: /scrape 123

Output: [Full workflow execution as described above]
```

### Example 3: Vivery Detected
```
User: /scrape 142

Output:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Selected Issue #142: Food Bank of the Rockies (CO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  VIVERY DETECTED

This site uses AccessFood widget and is covered by vivery_api_scraper.py

Close issue as vivery-covered? (recommended)
A) Yes, close issue
B) No, proceed anyway
C) Cancel

User: A

✓ Issue #142 closed with label 'vivery-covered'
✓ Comment added explaining Vivery coverage

Try: /scrape next (pick another issue)
```
