#!/bin/bash
# Initialize the data repository with proper structure for Datasette-Lite

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_REPO_PATH="${DATA_REPO_PATH:-$PROJECT_ROOT/../HAARRRvest}"
DATA_REPO_URL="${DATA_REPO_URL:-git@github.com:For-The-Greater-Good/HAARRRvest.git}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}Initializing HAARRRvest Data Repository${NC}"
echo "================================================"

# Step 1: Clone or create repository
if [ -d "$DATA_REPO_PATH" ]; then
    echo -e "${YELLOW}Data repository already exists at $DATA_REPO_PATH${NC}"
    cd "$DATA_REPO_PATH"
    git pull origin main || echo "Could not pull - repository might be new"
else
    echo -e "${GREEN}Creating data repository at $DATA_REPO_PATH${NC}"
    
    # Try to clone first
    if git clone "$DATA_REPO_URL" "$DATA_REPO_PATH" 2>/dev/null; then
        echo "✓ Cloned existing repository"
        cd "$DATA_REPO_PATH"
    else
        # Create new repository
        echo "Creating new repository..."
        mkdir -p "$DATA_REPO_PATH"
        cd "$DATA_REPO_PATH"
        git init
        git remote add origin "$DATA_REPO_URL" 2>/dev/null || echo "Remote might already exist"
    fi
fi

# Step 2: Create directory structure
echo -e "\n${GREEN}Creating directory structure...${NC}"
mkdir -p daily
mkdir -p latest
mkdir -p sqlite
mkdir -p .github/workflows

# Step 3: Create initial README
echo -e "\n${GREEN}Creating README...${NC}"
cat > README.md << 'EOF'
# HAARRRvest 🏴‍☠️

A treasure trove of food resource data harvested by Pantry Pirate Radio.

## 🔍 Explore the Data Interactively

### [**Launch Interactive Explorer →**](https://for-the-greater-good.github.io/HAARRRvest/)

Explore the data directly in your browser with SQL queries, no installation required!

## 📊 Quick Stats

- **Coverage**: United States
- **Standard**: [HSDS v3.1.1](https://docs.openreferral.org/en/latest/)
- **Update Frequency**: Daily
- **Format**: SQLite database with JSON archives

## 🗂️ Directory Structure

```
├── daily/                     # Historical data by date
│   └── YYYY-MM-DD/
│       ├── summary.json       # Daily summary
│       ├── scrapers/          # Raw scraper outputs
│       └── processed/         # LLM-processed data
├── latest/                    # Most recent data per scraper
├── sqlite/                    # SQLite database for queries
│   └── pantry_pirate_radio.sqlite
└── index.html                 # Interactive Datasette-Lite interface
```

## 🚀 Getting Started

### Browse Online
Visit our [GitHub Pages site](https://for-the-greater-good.github.io/HAARRRvest/) to explore the data interactively.

### Download Database
Download the [latest SQLite database](sqlite/pantry_pirate_radio.sqlite) to query locally.

### Clone Repository
```bash
git clone https://github.com/For-The-Greater-Good/HAARRRvest.git
cd HAARRRvest
```

## 📝 Example Queries

### Find Food Pantries by City
```sql
SELECT name, address_1, city, state_province, latitude, longitude
FROM locations
WHERE city = 'Brooklyn' AND state_province = 'NY'
ORDER BY name;
```

### Organizations with Multiple Locations
```sql
SELECT o.name, COUNT(l.id) as location_count
FROM organizations o
JOIN locations l ON o.id = l.organization_id
GROUP BY o.id, o.name
HAVING COUNT(l.id) > 5
ORDER BY location_count DESC;
```

### Services by Type
```sql
SELECT s.name, s.description, o.name as organization
FROM services s
JOIN organizations o ON s.organization_id = o.id
WHERE s.name LIKE '%food%' OR s.description LIKE '%pantry%'
LIMIT 20;
```

## 🛠️ Using the Data

### With Datasette
```bash
pip install datasette
datasette sqlite/pantry_pirate_radio.sqlite
```

### With Python
```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('sqlite/pantry_pirate_radio.sqlite')
df = pd.read_sql_query("SELECT * FROM locations WHERE state_province = 'NY'", conn)
```

### With DuckDB
```sql
-- Install and load SQLite extension
INSTALL sqlite_scanner;
LOAD sqlite_scanner;

-- Query the database
SELECT * FROM sqlite_scan('sqlite/pantry_pirate_radio.sqlite', 'locations');
```

## 📅 Update Schedule

- **Daily Updates**: New data is synchronized every day at 4 AM UTC
- **Real-time Status**: Check the [Actions tab](https://github.com/For-The-Greater-Good/pantry-pirate-radio/actions) for pipeline status
- **Last Update**: See [LAST_UPDATE.md](LAST_UPDATE.md) for details

## 📜 License

This data is provided under the [MIT License](https://github.com/For-The-Greater-Good/pantry-pirate-radio/blob/main/LICENSE).

## 🤝 Contributing

Found an issue with the data? Please [open an issue](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues) in the main repository.

## 📚 Learn More

- [Main Project Repository](https://github.com/For-The-Greater-Good/pantry-pirate-radio)
- [HSDS Specification](https://docs.openreferral.org/en/latest/)
- [API Documentation](https://github.com/For-The-Greater-Good/pantry-pirate-radio/blob/main/docs/api.md)
EOF

# Step 4: Create .gitignore
echo -e "\n${GREEN}Creating .gitignore...${NC}"
cat > .gitignore << 'EOF'
# OS files
.DS_Store
Thumbs.db

# Editor files
*.swp
*.swo
*~
.vscode/
.idea/

# Python
__pycache__/
*.py[cod]
.env
venv/
.virtualenvs/

# Temporary files
*.tmp
*.bak
*.log

# Large files (if needed)
*.zip
*.tar.gz
EOF

# Step 5: Create GitHub Actions workflow for Pages
echo -e "\n${GREEN}Creating GitHub Pages workflow...${NC}"
cat > .github/workflows/pages.yml << 'EOF'
name: Deploy GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup Pages
        uses: actions/configure-pages@v4
      
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '.'
      
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
EOF

# Step 6: Create initial index.html (will be replaced by publish script)
echo -e "\n${GREEN}Creating placeholder index.html...${NC}"
cp "$SCRIPT_DIR/datasette-lite-template.html" index.html 2>/dev/null || cat > index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>HAARRRvest - Food Resource Data Explorer</title>
    <meta charset="utf-8">
    <style>
        body { font-family: sans-serif; margin: 40px; text-align: center; }
        h1 { color: #333; }
        p { color: #666; margin: 20px 0; }
        .note { background: #f0f0f0; padding: 20px; border-radius: 8px; display: inline-block; }
    </style>
</head>
<body>
    <h1>🏴‍☠️ HAARRRvest - Data Explorer</h1>
    <div class="note">
        <p><strong>Coming Soon!</strong></p>
        <p>The interactive data explorer will be available after the first data sync.</p>
        <p>Check back shortly or visit our <a href="https://github.com/For-The-Greater-Good/pantry-pirate-radio">main repository</a>.</p>
    </div>
</body>
</html>
EOF

# Step 7: Create example SQLite file (placeholder)
echo -e "\n${GREEN}Creating placeholder files...${NC}"
touch sqlite/.gitkeep
touch daily/.gitkeep
touch latest/.gitkeep

# Step 8: Initial commit
echo -e "\n${GREEN}Creating initial commit...${NC}"
git add -A
git commit -m "Initial repository structure for Datasette-Lite

- Added README with usage instructions
- Created directory structure
- Added GitHub Pages workflow
- Added placeholder index.html" || echo "Nothing to commit"

# Step 9: Push to remote (optional)
echo -e "\n${BLUE}Repository initialized at: $DATA_REPO_PATH${NC}"
echo
echo "Next steps:"
echo "1. Push to GitHub: cd $DATA_REPO_PATH && git push -u origin main"
echo "2. Enable GitHub Pages in repository settings"
echo "3. Run the publish script to sync data"
echo "4. Visit https://[username].github.io/HAARRRvest/"
echo
echo -e "${GREEN}✓ Initialization complete!${NC}"