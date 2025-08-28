# HAARRRvest Quick Start Guide 🏴‍☠️

This guide will help you set up HAARRRvest, the data treasure trove for Pantry Pirate Radio.

## What is HAARRRvest?

HAARRRvest is the public data repository that makes food resource data accessible through:
- 🔍 Interactive SQL queries via Datasette-Lite
- 📊 Daily updated SQLite database
- 📁 Organized JSON archives
- 🌐 GitHub Pages hosting

## Prerequisites

- Docker and Docker Compose installed
- GitHub account with repository creation permissions
- Personal Access Token for GitHub (with `repo` scope)
- Git configured locally

## Step 1: Create the HAARRRvest Repository

1. Go to [GitHub](https://github.com/new)
2. Create a new repository named `HAARRRvest`
3. Set it as **Public** (for GitHub Pages)
4. Don't initialize with README (our script will do this)

## Step 2: Setup Pantry Pirate Radio Environment

```bash
# Clone Pantry Pirate Radio (the main project)
git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
cd pantry-pirate-radio

# Run the interactive setup wizard to configure your environment
./bouy setup

# The setup wizard will:
# - Create .env file from template
# - Configure database passwords
# - Set up LLM provider (OpenAI via OpenRouter or Claude/Anthropic)
# - Configure HAARRRvest repository tokens
# - Create timestamped backups of existing .env files
```

## Step 3: Configure HAARRRvest Publisher

The setup wizard will help configure these settings, or you can manually edit `.env`:

```bash
# HAARRRvest Repository Configuration
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_personal_access_token  # Required for push access

# Publisher Service Settings
PUBLISHER_CHECK_INTERVAL=300  # Check every 5 minutes (in seconds)
DAYS_TO_SYNC=7                # Sync last 7 days of data

# CRITICAL: Enable push only for production deployments
PUBLISHER_PUSH_ENABLED=false  # Set to 'true' ONLY for production
```

**⚠️ Important**: Keep `PUBLISHER_PUSH_ENABLED=false` for development to prevent accidental pushes to the public repository.

## Step 4: Enable GitHub Pages

1. Go to your HAARRRvest repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Choose **main** branch and **/ (root)** folder
5. Click **Save**

Wait 5-10 minutes for the initial deployment.

## Step 5: Start Services with Bouy

```bash
# Start all services (development mode by default)
./bouy up

# Or start with database initialization
./bouy up --with-init

# Monitor HAARRRvest publisher logs
./bouy haarrrvest logs

# Check publisher service status
./bouy haarrrvest status

# The publisher will:
# - Monitor recorder outputs every 5 minutes
# - Create date-based branches for safety (e.g., data-update-2025-01-27)
# - Export PostgreSQL to SQLite for Datasette
# - Generate map visualization data
# - Push updates to HAARRRvest repository (if PUBLISHER_PUSH_ENABLED=true)
```

## Step 6: Test the Pipeline

```bash
# Manually trigger publishing run
./bouy haarrrvest run

# Watch the logs to see it process files
./bouy haarrrvest logs

# Run tests to ensure everything works
./bouy test --pytest

# Check the HAARRRvest repository for updates
# Visit: https://github.com/For-The-Greater-Good/HAARRRvest
```

## Step 7: Run Scrapers to Generate Data

```bash
# List all available scrapers
./bouy scraper --list

# Run a specific scraper
./bouy scraper nyc_efap_programs

# Or run all scrapers sequentially
./bouy scraper --all

# Or run scrapers in parallel (scouting-party mode)
./bouy scraper scouting-party  # Default: 5 concurrent scrapers
./bouy scraper scouting-party 10  # Custom concurrency

# The data flows through this pipeline:
# 1. Scraper → Redis Queue
# 2. Worker → LLM Processing
# 3. Reconciler → Database
# 4. Recorder → JSON Files
# 5. Publisher → HAARRRvest Repository

# Monitor each stage:
./bouy logs worker
./bouy logs recorder
./bouy haarrrvest logs
```

## Step 8: Access Your Data

After the pipeline completes and GitHub Pages deploys:

### Via GitHub Pages (Public Access)
1. Visit: `https://datasette.for-the-gg.org`
2. Use Datasette-Lite to explore data with SQL queries
3. Download SQLite database for offline use
4. Share the link with your community!

### Via Local API (Development)
```bash
# API endpoints are available at:
# - REST API: http://localhost:8000/api/v1
# - Interactive Docs: http://localhost:8000/docs
# - ReDoc: http://localhost:8000/redoc
# - OpenAPI Schema: http://localhost:8000/openapi.json

# Example: Search for food services
curl "http://localhost:8000/api/v1/locations?latitude=40.7128&longitude=-74.0060&radius=5"
```

### Via Datasette (Production Mode)
```bash
# Start services in production mode
./bouy up --prod

# Access Datasette UI at:
# http://localhost:8001
```

## Automation

The HAARRRvest Publisher service runs continuously:

- **Automatic Checks**: Every 5 minutes (configurable)
- **On Startup**: Processes any pending files immediately
- **Branch Safety**: Creates date-based branches before merging
- **State Tracking**: Remembers processed files to avoid duplicates

No GitHub Actions needed - everything runs locally in your infrastructure!

## Troubleshooting

### Pages Not Loading
- Check GitHub Pages is enabled in repository Settings → Pages
- Verify index.html exists in HAARRRvest repository root
- Wait 10-15 minutes for initial deployment
- Check Actions tab for deployment errors
- Ensure repository is public (required for free GitHub Pages)

### Publisher Service Issues
- Verify DATABASE_URL is set correctly in `.env`
- Check DATA_REPO_TOKEN has write permissions (needs `repo` scope)
- Review logs: `./bouy haarrrvest logs`
- Ensure outputs directory has data: `./bouy exec app ls outputs/daily/`
- Check push permission: `PUBLISHER_PUSH_ENABLED` must be `true` for production
- Verify git authentication: Token needs full `repo` scope for private repos

### SQLite Not Loading
- Check file size (should be under 100MB)
- Verify path is correct in index.html
- Try downloading directly from repository

## Next Steps

1. **Customize the interface**: Edit index.html in HAARRRvest
2. **Add example queries**: Update README with useful SQL
3. **Monitor usage**: Check GitHub Insights
4. **Share widely**: Spread the word about open food data!

## Support

- [Main Project Issues](https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues)
- [Documentation](https://github.com/For-The-Greater-Good/pantry-pirate-radio/tree/main/docs)

Welcome aboard, data pirate! 🏴‍☠️ May your harvests be bountiful!