# GitHub Security Settings for Public Repository

This document outlines the critical security settings that must be configured in GitHub's UI before making this repository public. These settings work in conjunction with the GitHub Actions workflows defined in `.github/workflows/`.

## 1. Repository Settings

Navigate to Settings → General:

### Features
- [ ] **Wikis**: Disable (unless needed)
- [ ] **Issues**: Enable
- [ ] **Projects**: Disable (unless needed)
- [ ] **Discussions**: Optional

### Pull Requests
- [ ] **Allow merge commits**: Yes
- [ ] **Allow squash merging**: Yes
- [ ] **Allow rebase merging**: No (for cleaner history)
- [ ] **Automatically delete head branches**: Yes

### Danger Zone
- [ ] **Restrict forking**: Consider enabling initially

## 2. Branch Protection Rules

Navigate to Settings → Branches → Add rule for `main`:

### Protect matching branches
- [ ] **Require a pull request before merging**
  - [ ] Require approvals: 1
  - [ ] Dismiss stale pull request approvals when new commits are pushed
  - [ ] Require review from CODEOWNERS
  - [ ] Restrict who can dismiss pull request reviews: Repository admin only

### Status checks
- [ ] **Require status checks to pass before merging**
  - [ ] Require branches to be up to date before merging
  - Required status checks (from CI workflow):
    - `formatting-and-linting`
    - `mypy`
    - `pytest`
    - `bandit`
    - `safety`
    - `pip-audit`
    - `vulture`
    - `xenon`
    - `bouy-tests`

### Conversation resolution
- [ ] **Require conversation resolution before merging**

### Restrictions
- [ ] **Restrict who can push to matching branches**
  - Add: `For-The-Greater-Good`
- [ ] **Allow force pushes**: No
- [ ] **Allow deletions**: No

## 3. Actions Security

Navigate to Settings → Actions → General:

### Actions permissions
- [ ] **Allow owner, and select non-owner, actions and reusable workflows**
  - Allow actions created by GitHub
  - Allow specified actions and reusable workflows:
    ```
    actions/*
    docker/*
    anthropics/claude-code-action@beta
    softprops/action-gh-release@v1
    ```

### Workflow permissions
- [ ] **Read repository contents and packages permissions**
- [ ] **Allow GitHub Actions to create and approve pull requests**: No

### Artifact and log retention
- [ ] Set to 30 days (or your preference)

## 4. Secrets and Variables

Navigate to Settings → Secrets and variables → Actions:

### Repository Secrets
Create these secrets:
- [ ] `CLAUDE_CODE_OAUTH_TOKEN` - For Claude AI workflows (obtained from Claude Code GitHub integration)
- [ ] `OPENROUTER_API_KEY` - For LLM operations in CI tests (optional)

### Environments
Create these environments with protection rules:

#### `production` environment
- **Required reviewers**: For-The-Greater-Good
- **Deployment branches**: Only selected branches → main
- **Used by**: CD workflow for Docker image deployment
- Secrets:
  - `CLAUDE_CODE_OAUTH_TOKEN` (for Claude workflows)
  - Any production deployment secrets

#### `ci` environment
- **Deployment branches**: All branches
- **Used by**: CI workflow pytest job
- Secrets:
  - `OPENROUTER_API_KEY` (optional for LLM tests)

## 5. Security Features

Navigate to Settings → Code security and analysis:

### Security features
- [ ] **Dependency graph**: Enable
- [ ] **Dependabot alerts**: Enable
- [ ] **Dependabot security updates**: Enable
- [ ] **Secret scanning**: Enable
  - [ ] Push protection: Enable

### Code scanning
- [ ] **CodeQL analysis**: Set up (optional but recommended)

## 6. Webhook Security

Navigate to Settings → Webhooks:

- Review any existing webhooks
- Remove any unnecessary webhooks
- Ensure remaining webhooks use HTTPS and have secrets

## 7. Deploy Keys

Navigate to Settings → Deploy keys:

- Review any existing deploy keys
- Remove unused keys
- Ensure keys have appropriate read/write permissions

## 8. Integration with Bouy

### Local Testing Before Deployment
Use bouy commands to verify your setup:
```bash
# Test all CI checks locally
./bouy test

# Individual test categories
./bouy test --pytest    # Run tests
./bouy test --mypy      # Type checking
./bouy test --black     # Formatting
./bouy test --ruff      # Linting
./bouy test --bandit    # Security
./bouy test --vulture   # Dead code
./bouy test --safety    # Dependencies
./bouy test --pip-audit # Vulnerability scan
./bouy test --xenon     # Complexity
```

## 9. Additional Recommendations

### Before Going Public
1. **Audit commit history**: Ensure no secrets in history
2. **Review all branches**: Delete unnecessary branches
3. **Check releases**: Remove any pre-release versions with issues
4. **Review GitHub Apps**: Remove unnecessary integrations
5. **Test workflows**: Run `./bouy test` locally to ensure CI will pass

### After Going Public
1. **Monitor security alerts**: Check weekly
2. **Review pull requests**: Especially from first-time contributors
3. **Update dependencies**: Monthly security patches
4. **Audit workflow runs**: Check for suspicious activity

### Community Standards
Consider adding:
- [ ] Contributing guidelines (`CONTRIBUTING.md`)
- [ ] Code of Conduct (`CODE_OF_CONDUCT.md`)
- [ ] Issue templates (`.github/ISSUE_TEMPLATE/`)
- [ ] Pull request template (`.github/pull_request_template.md`)

## Verification Checklist

After applying all settings, verify:

1. [ ] Try to push directly to main (should fail)
2. [ ] Create a PR without CI passing (should not allow merge)
3. [ ] Try to modify workflows as external contributor (should require approval)
4. [ ] Attempt to trigger Claude workflows from fork (should fail due to owner restrictions)
5. [ ] Check that secrets are not exposed in logs
6. [ ] Verify CODEOWNERS is enforced
7. [ ] Run `./bouy test` locally to ensure CI checks work
8. [ ] Verify CD workflow triggers on main branch push
9. [ ] Check Docker images are published to `ghcr.io`
10. [ ] Confirm environments (`ci` and `production`) are properly configured

## Emergency Response

If security incident occurs:
1. **Immediately**: Set repository to private
2. **Revoke**: All potentially compromised secrets
3. **Audit**: Recent commits and workflow runs
4. **Report**: Use GitHub's security advisory feature
5. **Fix**: Address the vulnerability
6. **Communicate**: Notify affected users if needed