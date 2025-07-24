# Publishing Datasette on GitHub

This guide covers various ways to publish your SQLite database interactively on GitHub.

## Option 1: GitHub Pages with Datasette-Lite (Recommended)

Datasette-Lite runs entirely in the browser using WebAssembly - no server needed!

### Setup Instructions

1. **Create GitHub Pages site** in your data repository:

```yaml
# .github/workflows/publish-datasette-lite.yml
name: Publish Datasette-Lite to GitHub Pages

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

      - name: Create Datasette-Lite HTML
        run: |
          mkdir -p _site
          cat > _site/index.html << 'EOF'
          <!DOCTYPE html>
          <html>
          <head>
              <title>Pantry Pirate Radio - Food Resources Data</title>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <style>
                  body { margin: 0; font-family: sans-serif; }
                  #header { 
                      background: #333; 
                      color: white; 
                      padding: 1rem; 
                      text-align: center;
                  }
                  #header h1 { margin: 0; }
                  #header p { margin: 0.5rem 0 0 0; opacity: 0.8; }
                  iframe { 
                      width: 100%; 
                      height: calc(100vh - 100px); 
                      border: none; 
                  }
              </style>
          </head>
          <body>
              <div id="header">
                  <h1>🏴‍☠️ Pantry Pirate Radio - Food Resources</h1>
                  <p>Explore food assistance locations with interactive SQL queries</p>
              </div>
              <iframe src="https://lite.datasette.io/?url=https://raw.githubusercontent.com/For-The-Greater-Good/HAARRRvest/main/sqlite/pantry_pirate_radio.sqlite#/pantry_pirate_radio"></iframe>
          </body>
          </html>
          EOF

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: '_site'

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

2. **Enable GitHub Pages** in repository settings:
   - Go to Settings → Pages
   - Source: GitHub Actions
   - Your data will be available at: `https://for-the-greater-good.github.io/HAARRRvest/`

## Option 2: Observable Notebooks

Create interactive data visualizations with Observable:

```javascript
// Create a notebook at observablehq.com
// Import your data
db = {
  const url = "https://raw.githubusercontent.com/For-The-Greater-Good/HAARRRvest/main/sqlite/pantry_pirate_radio.sqlite"
  const sqljs = await require("sql.js@1.8.0")
  const SQL = await sqljs();
  const buf = await fetch(url).then(d => d.arrayBuffer());
  return new SQL.Database(new Uint8Array(buf));
}

// Query the data
locations = db.exec("SELECT * FROM locations WHERE state = 'NY' LIMIT 100")[0]

// Create interactive map
Plot.plot({
  projection: "albers-usa",
  marks: [
    Plot.geo(usStates, {fill: "lightgray"}),
    Plot.dot(locations, {
      x: d => d.longitude,
      y: d => d.latitude,
      r: 3,
      fill: "red",
      title: d => d.name
    })
  ]
})
```

## Option 3: GitHub Flat Data

Use GitHub's Flat Data Action to create visualizations:

```yaml
# .github/workflows/flat.yml
name: Flat Data

on:
  push:
    paths:
      - sqlite/pantry_pirate_radio.sqlite
  workflow_dispatch:

jobs:
  scheduled:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repo
        uses: actions/checkout@v3
      
      - name: Setup duckdb
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install duckdb pandas
      
      - name: Extract data to CSV
        run: |
          python << 'EOF'
          import duckdb
          import pandas as pd
          
          # Connect to SQLite
          conn = duckdb.connect()
          conn.execute("INSTALL sqlite_scanner;")
          conn.execute("LOAD sqlite_scanner;")
          
          # Export tables to CSV
          tables = ['organizations', 'locations', 'services']
          for table in tables:
              df = conn.execute(f"""
                  SELECT * FROM sqlite_scan('sqlite/pantry_pirate_radio.sqlite', '{table}')
              """).df()
              df.to_csv(f'data/{table}.csv', index=False)
          EOF
      
      - name: Commit and push
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add data/*.csv
          git commit -m "Update CSV exports" || exit 0
          git push
```

## Option 4: Datasette Cloud (Easiest)

Deploy to Datasette Cloud for instant hosting:

```bash
# Install datasette-publish-datasette-cloud
pip install datasette-publish-datasette-cloud

# Publish (requires account at datasette.cloud)
datasette publish datasette-cloud pantry_pirate_radio.sqlite \
    --project pantry-pirate-radio \
    --title "Pantry Pirate Radio - Food Resources"
```

## Option 5: Vercel Deployment

Deploy Datasette as a serverless function:

```bash
# Install datasette-publish-vercel
pip install datasette-publish-vercel

# Create vercel.json
cat > vercel.json << 'EOF'
{
  "builds": [
    {
      "src": "*.sqlite",
      "use": "@vercel/static"
    }
  ]
}
EOF

# Deploy
datasette publish vercel pantry_pirate_radio.sqlite \
    --project pantry-pirate-radio \
    --metadata metadata.json
```

## Option 6: GitHub Codespaces Integration

Add a `.devcontainer/devcontainer.json` to your data repo:

```json
{
  "name": "Pantry Pirate Radio Data Explorer",
  "image": "mcr.microsoft.com/devcontainers/python:3.11",
  "features": {
    "ghcr.io/devcontainers/features/sqlite:1": {}
  },
  "postCreateCommand": "pip install datasette datasette-cluster-map datasette-vega && datasette pantry_pirate_radio.sqlite --host 0.0.0.0",
  "forwardPorts": [8001],
  "customizations": {
    "vscode": {
      "extensions": ["mtxr.sqltools", "mtxr.sqltools-driver-sqlite"]
    }
  }
}
```

## Option 7: SQL.js Playground

Create a simple HTML file in your repo:

```html
<!-- explore.html -->
<!DOCTYPE html>
<html>
<head>
    <title>SQL Explorer - Pantry Pirate Radio</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/sql-wasm.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/codemirror.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.2/mode/sql/sql.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        #editor { height: 150px; border: 1px solid #ddd; }
        #results { margin-top: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        button { margin: 10px 0; padding: 10px 20px; }
    </style>
</head>
<body>
    <h1>🏴‍☠️ Pantry Pirate Radio - SQL Explorer</h1>
    <p>Query the food resources database directly in your browser!</p>
    
    <div id="editor">SELECT name, address_1, city, state_province 
FROM locations 
WHERE state_province = 'NY' 
LIMIT 10;</div>
    
    <button onclick="runQuery()">Run Query</button>
    
    <div id="results"></div>

    <script>
        let db;
        const editor = CodeMirror.fromTextArea(document.getElementById('editor'), {
            mode: 'text/x-sql',
            lineNumbers: true
        });

        // Load the database
        initSqlJs({
            locateFile: file => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}`
        }).then(SQL => {
            fetch('sqlite/pantry_pirate_radio.sqlite')
                .then(res => res.arrayBuffer())
                .then(buf => {
                    db = new SQL.Database(new Uint8Array(buf));
                    console.log('Database loaded!');
                });
        });

        function runQuery() {
            if (!db) {
                alert('Database is still loading...');
                return;
            }

            const query = editor.getValue();
            const resultsDiv = document.getElementById('results');
            
            try {
                const result = db.exec(query);
                if (result.length === 0) {
                    resultsDiv.innerHTML = '<p>Query executed successfully, no results.</p>';
                    return;
                }

                let html = '<table><tr>';
                result[0].columns.forEach(col => {
                    html += `<th>${col}</th>`;
                });
                html += '</tr>';

                result[0].values.forEach(row => {
                    html += '<tr>';
                    row.forEach(val => {
                        html += `<td>${val}</td>`;
                    });
                    html += '</tr>';
                });
                html += '</table>';
                
                resultsDiv.innerHTML = html;
            } catch (e) {
                resultsDiv.innerHTML = `<p style="color: red;">Error: ${e.message}</p>`;
            }
        }
    </script>
</body>
</html>
```

## Comparison of Options

| Option | Pros | Cons | Best For |
|--------|------|------|----------|
| **Datasette-Lite** | No server needed, instant loading, full Datasette features | Limited to smaller databases (<100MB) | Quick sharing, demos |
| **Observable** | Rich visualizations, notebooks, community | Requires Observable account | Data storytelling |
| **Flat Data** | Automated updates, GitHub integration | CSV only, no SQL interface | Simple data files |
| **Datasette Cloud** | Full features, managed hosting | Requires subscription | Production use |
| **Vercel** | Free tier, serverless | Cold starts, complexity | Medium traffic |
| **Codespaces** | Full dev environment, VS Code | Requires GitHub account | Development |
| **SQL.js** | Simple, customizable | Basic features only | Custom interfaces |

## Quick Start: Datasette-Lite

The fastest way to get started:

1. Add this to your data repo's README.md:

```markdown
## Explore the Data

[🔍 **Open in Datasette-Lite**](https://lite.datasette.io/?url=https://raw.githubusercontent.com/For-The-Greater-Good/HAARRRvest/main/sqlite/pantry_pirate_radio.sqlite#/pantry_pirate_radio)

This opens an interactive SQL interface right in your browser - no installation needed!
```

2. For a custom interface, create `index.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Food Resources Explorer</title>
    <meta http-equiv="refresh" content="0; url=https://lite.datasette.io/?url=https://raw.githubusercontent.com/For-The-Greater-Good/HAARRRvest/main/sqlite/pantry_pirate_radio.sqlite">
</head>
<body>
    <p>Redirecting to Datasette-Lite...</p>
</body>
</html>
```

3. Enable GitHub Pages and your data is live!

## Advanced: Custom Datasette Plugins

For Datasette-Lite, you can specify plugins via URL:

```
https://lite.datasette.io/?url=YOUR_SQLITE_URL&install=datasette-cluster-map&install=datasette-vega
```

Or create a custom deployment with metadata:

```json
{
  "title": "Pantry Pirate Radio - Food Resources",
  "description": "Open data for food assistance locations",
  "plugins": {
    "datasette-cluster-map": {
      "latitude_column": "latitude",
      "longitude_column": "longitude"
    }
  }
}
```