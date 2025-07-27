# GitHub Repository Settings Migration Guide

This guide explains how to migrate GitHub repository settings to Infrastructure as Code (IaC) when recreating or moving repositories.

## Overview

We use a GitHub Actions-based approach to manage repository settings as code, providing:

- Version control for all repository settings
- Automated synchronization of settings
- Complete control without external dependencies
- Support for all GitHub features including environments

## Migration Components

### 1. Settings Configuration File

**Location**: `.github/settings.yml`

This YAML file contains all repository settings including:

- Repository metadata (name, description, visibility)
- Feature toggles (issues, wiki, projects)
- Merge settings
- Labels with colors and descriptions
- Branch protection rules

### 2. Settings Sync Workflow

**Location**: `.github/workflows/sync-repository-settings.yml`

A GitHub Actions workflow that:

- Reads the settings.yml file
- Applies settings using the GitHub CLI (`gh`)
- Supports dry-run mode for testing
- Runs automatically on settings changes or manually

### 3. Environment Setup Script

**Location**: `.github/scripts/setup-environments.sh`

A bash script that recreates:

- CI environment (no protection rules)
- Production environment (with branch deployment policies)
- Instructions for adding secrets

## Migration Steps

### Step 1: Initial Repository Setup

1. Create your new repository on GitHub:

   ```bash
   gh repo create For-The-Greater-Good/pantry-pirate-radio --private
   ```

2. Clone the repository and add your code:

   ```bash
   git clone https://github.com/For-The-Greater-Good/pantry-pirate-radio.git
   cd pantry-pirate-radio
   # Add your code files
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

### Step 2: Configure Personal Access Token (Required for Full Functionality)

1. Create a Personal Access Token with `repo` scope:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select the `repo` scope
   - Generate and copy the token

2. Add the PAT as a repository secret:
   ```bash
   gh secret set REPO_SETTINGS_PAT --body 'your-pat-here' --repo For-The-Greater-Good/pantry-pirate-radio
   ```

### Step 3: Apply Repository Settings

1. Ensure the settings files are in place:
   - `.github/settings.yml`
   - `.github/workflows/sync-repository-settings.yml`

2. Push the settings to the repository:

   ```bash
   git add .github/settings.yml .github/workflows/sync-repository-settings.yml
   git commit -m "Add repository settings configuration"
   git push origin main
   ```

3. Run the settings sync workflow:

   ```bash
   # First, do a dry run to see what will change
   gh workflow run sync-repository-settings.yml -f dry_run=true

   # Check the workflow run
   gh run list --workflow=sync-repository-settings.yml

   # If everything looks good, run it for real
   gh workflow run sync-repository-settings.yml -f dry_run=false
   ```

### Step 4: Setup Environments

Run the environment setup script:

```bash
# Make sure you're in the repository directory
./.github/scripts/setup-environments.sh

# Or specify the repository explicitly
./.github/scripts/setup-environments.sh For-The-Greater-Good/pantry-pirate-radio
```

### Step 5: Add Secrets

Add repository secrets (these cannot be stored in code for security reasons):

```bash
# Add OpenRouter API key
gh secret set OPENROUTER_API_KEY --repo For-The-Greater-Good/pantry-pirate-radio

# Add Claude Code OAuth token
gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo For-The-Greater-Good/pantry-pirate-radio
```

### Step 6: Verify Settings

1. Check repository settings:

   ```bash
   gh repo view For-The-Greater-Good/pantry-pirate-radio --json name,description,visibility,hasIssuesEnabled,hasWikiEnabled
   ```

2. Check branch protection:

   ```bash
   gh api repos/For-The-Greater-Good/pantry-pirate-radio/branches/main/protection
   ```

3. Check environments:

   ```bash
   gh api repos/For-The-Greater-Good/pantry-pirate-radio/environments
   ```

4. Check labels:

   ```bash
   gh api repos/For-The-Greater-Good/pantry-pirate-radio/labels
   ```

## Customizing Settings

### Modifying Repository Settings

Edit `.github/settings.yml` and update any settings:

```yaml
repository:
  description: "Your new description"
  topics: topic1, topic2, topic3
  private: true  # or false for public
```

### Adding New Labels

Add to the `labels` section in `.github/settings.yml`:

```yaml
labels:
  - name: priority-high
    color: FF0000
    description: High priority issue
```

### Updating Branch Protection

Modify the `branches` section in `.github/settings.yml`:

```yaml
branches:
  - name: main
    protection:
      required_status_checks:
        contexts:
          - "new-check-name"
```

### After Making Changes

1. Commit and push your changes
2. The workflow will run automatically, or trigger it manually:

   ```bash
   gh workflow run sync-repository-settings.yml -f dry_run=false
   ```

## Troubleshooting

### Workflow Permissions

If the workflow fails with permission errors:

1. Check repository settings → Actions → General
2. Under "Workflow permissions", ensure it has read and write permissions
3. Enable "Allow GitHub Actions to create and approve pull requests" if needed

### Branch Protection Conflicts

If branch protection fails to apply:

1. Ensure the branch exists before applying protection
2. Check that status check names match exactly (case-sensitive)
3. Verify you have admin permissions on the repository

### Environment Setup Issues

If environments fail to create:

1. Ensure you have admin access to the repository
2. For private repositories, ensure you have the appropriate GitHub plan
3. Check the GitHub API response for specific error messages

## Best Practices

1. **Test with Dry Run**: Always test changes with `dry_run=true` first
2. **Version Control**: Commit all settings changes with descriptive messages
3. **Documentation**: Update this guide when adding new settings types
4. **Security**: Never commit secrets or sensitive data to the repository
5. **Regular Sync**: Run the sync workflow after major repository changes

## Alternative: Using Probot Settings App

If you prefer a simpler approach with automatic syncing:

1. Install the [Settings Probot app](https://github.com/apps/settings)
2. Use the same `.github/settings.yml` file
3. Changes are applied automatically when merged to the default branch

Note: The Probot app has limitations:

- Cannot manage environments
- Security concern: anyone with push access can change settings
- Requires external app permissions

## Summary

This IaC approach ensures your GitHub repository settings are:

- Version controlled and reviewable
- Easily reproducible across repositories
- Automatically synchronized
- Fully auditable through git history

When recreating or migrating repositories, simply copy these files and run the setup process to restore all settings.
