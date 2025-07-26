# HAARRRvest Quick Start Guide 🏴‍☠️

This guide will help you set up HAARRRvest, the data treasure trove for Pantry Pirate Radio.

## What is HAARRRvest?

HAARRRvest is the public data repository that makes food resource data accessible through:
- 🔍 Interactive SQL queries via Datasette-Lite
- 📊 Daily updated SQLite database
- 📁 Organized JSON archives
- 🌐 GitHub Pages hosting

## Prerequisites

- GitHub account with repository creation permissions
- Git configured with SSH keys
- Personal Access Token for GitHub Actions

## Step 1: Create the HAARRRvest Repository

1. Go to [GitHub](https://github.com/new)
2. Create a new repository named `HAARRRvest`
3. Set it as **Public** (for GitHub Pages)
4. Don't initialize with README (our script will do this)

## Step 2: Clone and Setup HAARRRvest

```bash
# Clone the HAARRRvest repository
git clone https://github.com/For-The-Greater-Good/HAARRRvest.git
cd HAARRRvest

# The repository structure will be automatically created by the publisher service:
# - daily/ (historical data by date)
# - latest/ (most recent data)
# - sqlite/ (SQLite database exports)
# - data/ (map visualization data)
```

## Step 3: Configure Publisher Service

The HAARRRvest Publisher service now handles all data publishing automatically:

```bash
# In your pantry-pirate-radio .env file, add:
DATA_REPO_URL=https://github.com/For-The-Greater-Good/HAARRRvest.git
DATA_REPO_TOKEN=your_github_personal_access_token
PUBLISHER_CHECK_INTERVAL=300  # Check every 5 minutes
DAYS_TO_SYNC=7  # Sync last 7 days of data
```

## Step 4: Enable GitHub Pages

1. Go to your HAARRRvest repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Choose **main** branch and **/ (root)** folder
5. Click **Save**

Wait 5-10 minutes for the initial deployment.

## Step 5: Start the Publisher Service

```bash
# Start all services including the publisher
docker-compose up -d

# Monitor publisher logs
docker-compose logs -f haarrrvest-publisher

# The publisher will:
# - Monitor recorder outputs every 5 minutes
# - Create date-based branches for safety
# - Export PostgreSQL to SQLite
# - Generate map visualization data
# - Push updates to HAARRRvest repository
```

## Step 6: Test the Pipeline

```bash
# Manually trigger publishing by restarting the service
docker-compose restart haarrrvest-publisher

# Watch the logs to see it process files
docker-compose logs -f haarrrvest-publisher

# Check the HAARRRvest repository for updates
# Visit: https://github.com/For-The-Greater-Good/HAARRRvest
```

## Step 7: Run a Scraper to Generate Data

```bash
# Run a scraper to generate some data
docker-compose exec scraper python -m app.scraper nyc_efap_programs

# The data will flow through:
# 1. Scraper → Redis Queue
# 2. Worker → LLM Processing
# 3. Reconciler → Database
# 4. Recorder → JSON Files
# 5. Publisher → HAARRRvest Repository

# Monitor each stage:
docker-compose logs -f worker
docker-compose logs -f recorder
docker-compose logs -f haarrrvest-publisher
```

## Step 8: Access Your Data

After the pipeline completes and GitHub Pages deploys:

1. Visit: `https://for-the-greater-good.github.io/HAARRRvest/`
2. Explore data with SQL queries
3. Download SQLite database
4. Share with your community!

## Automation

The HAARRRvest Publisher service runs continuously:

- **Automatic Checks**: Every 5 minutes (configurable)
- **On Startup**: Processes any pending files immediately
- **Branch Safety**: Creates date-based branches before merging
- **State Tracking**: Remembers processed files to avoid duplicates

No GitHub Actions needed - everything runs locally in your infrastructure!

## Troubleshooting

### Pages Not Loading
- Check GitHub Pages is enabled
- Verify index.html exists in repository
- Wait 10-15 minutes for deployment
- Check Actions tab for errors

### Publisher Service Issues
- Verify DATABASE_URL is set correctly
- Check DATA_REPO_TOKEN has write permissions
- Review logs: `docker-compose logs haarrrvest-publisher`
- Ensure outputs directory has data: `ls outputs/daily/`
- Check git authentication: Token needs `repo` scope

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