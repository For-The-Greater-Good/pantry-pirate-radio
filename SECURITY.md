# Security Policy

This document outlines the security measures, vulnerability disclosure process, and best practices for the Pantry Pirate Radio project.

## Vulnerability Disclosure

### Reporting Security Issues

If you discover a security vulnerability in this project, please report it privately to maintain the security of our users.

**DO NOT** create a public GitHub issue for security vulnerabilities.

### How to Report

1. **Email**: Send details to the repository maintainers via GitHub private message
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

### Response Process

1. **Acknowledgment**: We will acknowledge receipt within 48 hours
2. **Investigation**: We will investigate and assess the vulnerability
3. **Fix**: We will develop and test a fix
4. **Disclosure**: We will coordinate public disclosure after the fix is available

## Security Configuration

### Environment Variables

#### Never Commit Secrets

The `.env` file contains sensitive information and should **NEVER** be committed to version control. We provide `.env.example` as a template with dummy values.

### Setup Instructions

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your actual values:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key
   - `POSTGRES_PASSWORD`: A strong database password
   - Other sensitive configuration as needed

3. The `.env` file is gitignored to prevent accidental commits.

## Git Hooks

### Pre-commit Security Checks

We use a pre-commit hook to prevent accidentally committing secrets. The hook automatically scans for:

- API keys (OpenRouter, OpenAI, AWS, etc.)
- Passwords in configuration files
- Private keys and certificates
- Other sensitive file patterns

### Enabling Git Hooks

The hooks are already configured in the repository. To activate them:

```bash
git config core.hooksPath .githooks
```

This command is included in the setup instructions and ensures the pre-commit hook runs before every commit.

### Bypassing Hooks (Use Carefully)

If you encounter a false positive, you can bypass the hook with:

```bash
git commit --no-verify
```

**Warning**: Only use this if you're certain no secrets are being committed.

## Security Patterns Detected

The enhanced pre-commit hook detects:

### 1. **Secrets and Credentials**
- **API Keys**: OpenRouter keys, OpenAI keys, AWS access keys, generic API key patterns
- **Passwords**: Database passwords, service passwords, hardcoded credentials
- **Private Keys**: SSH keys, SSL certificates, PGP keys
- **Sensitive Files**: `.env` files, `.pem`, `.key` files, identity files

### 2. **Personal Identifiable Information (PII)**
- **Phone Numbers**: Real phone numbers (non-555 format) in data files
- **Email Addresses**: Real email addresses (non-example.com/test.com domains)
- **Social Security Numbers**: SSN patterns in any format
- **Street Addresses**: Real street addresses in data files

### 3. **Configuration Security**
- **Hardcoded Credentials**: API keys and passwords in configuration files
- **Internal Infrastructure**: Private IP addresses and internal domain names

### 4. **Data File Security**
The hook specifically checks data files (`.csv`, `.json`, `.xml`, `.xlsx`, `.tsv`) for:
- Real contact information that should be anonymized
- Test data that doesn't follow security guidelines
- Accidentally committed production data

## Best Practices

### General Security
1. **Use Environment Variables**: Never hardcode secrets in source code
2. **Rotate Keys Regularly**: If a key is exposed, rotate it immediately
3. **Use `.env.example`**: Document required variables without exposing values
4. **Review Before Commit**: Always review your changes before committing
5. **Check Git History**: Ensure no secrets exist in previous commits before making the repository public

### Test Data Guidelines
6. **Anonymize Test Data**: Never use real personal information in test data
7. **Use 555 Phone Numbers**: For test phone numbers, use format `555-xxx-xxxx` or `(555) xxx-xxxx`
8. **Use Example Domains**: For test emails, use `example.com`, `test.com`, or `localhost`
9. **Fake Addresses**: Use obviously fake addresses like `123 Test Street, Example City, ST 12345`
10. **Regular Audits**: Periodically review data files for accidentally committed real data

### Data File Security
11. **Minimize Data Exposure**: Only include necessary data in test files
12. **Regular Cleanup**: Remove old test data files that are no longer needed
13. **Document Data Sources**: Clearly mark the origin and purpose of any data files

## Incident Response

If secrets are accidentally committed:

1. **Rotate the exposed credentials immediately**
2. **Remove from history** (if repository is private):
   ```bash
   # Use BFG Repo-Cleaner or git filter-branch
   # Example with BFG:
   bfg --delete-files .env
   git push --force
   ```
3. **For public repositories**: Consider the secrets permanently compromised and rotate all credentials

## Additional Security Measures

- All services run in Docker containers with limited privileges
- Database connections use strong passwords
- Redis is not exposed to the public internet
- API endpoints use CORS restrictions
- Input validation on all user-provided data
- Regular security scanning with Bandit