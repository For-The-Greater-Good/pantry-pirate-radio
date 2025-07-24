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

## Step 2: Initialize the Repository

```bash
# From the pantry-pirate-radio directory
./scripts/init-data-repo.sh

# This will:
# - Clone/create the repository
# - Set up directory structure
# - Create README and index.html
# - Configure GitHub Actions for Pages
```

## Step 3: Push Initial Structure

```bash
cd ../HAARRRvest
git push -u origin main
```

## Step 4: Enable GitHub Pages

1. Go to your HAARRRvest repository on GitHub
2. Navigate to **Settings** → **Pages**
3. Under **Source**, select **Deploy from a branch**
4. Choose **main** branch and **/ (root)** folder
5. Click **Save**

Wait 5-10 minutes for the initial deployment.

## Step 5: Configure Main Repository

1. Add GitHub Secret to pantry-pirate-radio repository:
   - Go to **Settings** → **Secrets and variables** → **Actions**
   - Add new secret: `DATA_REPO_TOKEN`
   - Value: Personal Access Token with `repo` scope

2. Update your `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env to add your database connection and other settings
   ```

## Step 6: Test the Pipeline

```bash
# Run a test sync (without pushing)
DAYS_TO_SYNC=1 PUSH_TO_REMOTE=false ./scripts/publish-data.sh

# Check the results
cd ../HAARRRvest
git status
```

## Step 7: Run Full Pipeline

```bash
# Run the complete pipeline
./scripts/publish-data.sh

# This will:
# 1. Organize recorder outputs
# 2. Sync to HAARRRvest repository
# 3. Rebuild database from JSON
# 4. Export to SQLite
# 5. Create Datasette-Lite interface
# 6. Push everything to GitHub
```

## Step 8: Access Your Data

After the pipeline completes and GitHub Pages deploys:

1. Visit: `https://for-the-greater-good.github.io/HAARRRvest/`
2. Explore data with SQL queries
3. Download SQLite database
4. Share with your community!

## Automation

Enable automatic daily updates:

1. Go to pantry-pirate-radio repository
2. Navigate to **Actions** → **Publish Data to Repository**
3. Enable the workflow
4. It will run daily at 4 AM UTC

## Troubleshooting

### Pages Not Loading
- Check GitHub Pages is enabled
- Verify index.html exists in repository
- Wait 10-15 minutes for deployment
- Check Actions tab for errors

### Pipeline Failures
- Verify DATABASE_URL is set correctly
- Check DATA_REPO_TOKEN has write permissions
- Review logs in GitHub Actions
- Ensure outputs directory has data

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