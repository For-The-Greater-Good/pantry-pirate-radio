# Security Policy

> **📚 Related Documentation**: For complete project documentation including architecture, deployment, and development guides, see the **[Documentation Hub](docs/INDEX.md)**.

## Supported Versions

We release patches for security vulnerabilities. Which versions are eligible for receiving such patches depends on the CVSS v3.0 Rating:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| main branch | :white_check_mark: |
| develop branch | :warning: Development only |

## Reporting a Vulnerability

Please report security vulnerabilities to the maintainers by opening a security advisory on GitHub:

1. Go to the Security tab in the repository
2. Click on "Report a vulnerability" button
3. Fill out the vulnerability report form with detailed information
4. **DO NOT** create a public issue for security vulnerabilities

### What to Include in Your Report

- **Issue Type**: Specify the vulnerability category (e.g., SQL injection, XSS, authentication bypass, PII exposure, secret leakage)
- **Affected Components**: Full paths of source file(s) related to the issue
- **Location**: The exact location of affected code (branch/commit/tag or direct URL)
- **Environment**: Configuration required to reproduce (Docker setup, environment variables)
- **Reproduction Steps**: Detailed step-by-step instructions using bouy commands where applicable
- **Proof of Concept**: Exploit code or demonstration (if possible)
- **Impact Assessment**: How an attacker might exploit this issue and potential damage
- **Suggested Fix**: If you have a proposed solution, please include it

### Response Timeline

- We will acknowledge receipt of your vulnerability report within 48 hours
- We will provide an initial assessment within 7 days
- We will work on fixes and coordinate disclosure timelines with you

## Security Best Practices

### For Contributors

1. **Never Commit Secrets**:
   - API keys, passwords, or tokens must never be committed to version control
   - Use `.env` files (never commit these) or environment variables
   - Run `./bouy setup` to configure secrets safely
   - All secrets are validated during the setup process

2. **Use Environment Variables**:
   - All sensitive configuration must come from environment variables
   - Use the `.env.example` template as reference
   - Configure secrets through `./bouy setup` wizard
   - Never hardcode credentials in source code

3. **Follow Secure Coding Practices**:
   - Input validation on all user-provided data
   - Parameterized queries via SQLAlchemy (no raw SQL)
   - Output encoding for API responses
   - Proper error handling without exposing sensitive details
   - Use type hints and Pydantic models for validation

4. **Dependency Management**:
   - Keep all dependencies updated via Poetry
   - Run security scans regularly: `./bouy test --bandit`
   - Check for vulnerabilities: `./bouy test --safety`
   - Audit pip packages: `./bouy test --pip-audit`
   - Monitor GitHub Dependabot alerts

### For Users

1. **Initial Setup Security**:
   - Run `./bouy setup` for secure initial configuration
   - Use strong passwords for database (not the default 'pirate' in production)
   - Configure proper API keys for LLM providers
   - Keep `.env` file permissions restricted (chmod 600)

2. **Secret Management**:
   - Rotate API keys and passwords regularly
   - Use different credentials for dev/test/production
   - Store production secrets in secure secret management systems
   - Never share `.env` files or commit them to repositories

3. **Monitoring and Auditing**:
   - Check logs regularly: `./bouy logs app`
   - Monitor RQ Dashboard for job anomalies: http://localhost:9181
   - Review API access patterns: `./bouy logs app | grep API`
   - Enable correlation IDs for request tracking

## Security Features

This application implements comprehensive security measures:

### Application Security
- **Input Validation**: All inputs validated via Pydantic models and type hints
- **SQL Injection Prevention**: Parameterized queries through SQLAlchemy ORM
- **Rate Limiting**: API endpoints protected against abuse (configurable limits)
- **Security Headers**: CORS, CSP, and other security headers via middleware
- **Geographic Data Validation**: Coordinates validated to prevent injection attacks
- **Error Handling**: Secure error messages without exposing system details

### Testing and Scanning
- **Security Testing**: Run with `./bouy test --bandit`
- **Dependency Scanning**: `./bouy test --safety` and `./bouy test --pip-audit`
- **Code Quality**: `./bouy test --mypy` for type safety
- **Dead Code Detection**: `./bouy test --vulture`
- **Complexity Analysis**: `./bouy test --xenon`
- **GitHub Security**: Dependabot and secret scanning enabled
- **CI/CD Pipeline**: All security checks run automatically on PRs

### Infrastructure Security
- **Containerization**: All services run in isolated Docker containers
- **Network Isolation**: Services communicate through Docker networks
- **Database Security**: PostGIS with proper access controls
- **Redis Security**: Protected Redis instance for job queues
- **No Root Containers**: All containers run as non-root users

## Known Security Considerations

### Design Decisions
- **Public API**: No authentication required by design for food resource access
- **Public Data Only**: All data served is publicly available information
- **No PII Collection**: System does not collect or store personal user data
- **Read-Only Access**: Public API endpoints are read-only
- **Write Operations**: Only internal services can modify data

### Test Data Security
- **Never use real PII** in test data or examples
- **Phone numbers**: Use 555-xxx-xxxx format only
- **Email addresses**: Use example.com, test.com, or localhost domains
- **Addresses**: Use clearly fictional addresses
- **Names**: Use placeholder names (John Doe, Test Organization)

### Scraper Security
- **Rate Limiting**: All scrapers implement respectful rate limiting
- **robots.txt Compliance**: Scrapers respect robots.txt directives
- **User-Agent Headers**: Proper identification in scraper requests
- **No Credential Harvesting**: Scrapers only collect public data

## Security Testing

### Running Security Checks

```bash
# Run all security tests
./bouy test --bandit         # Security linting
./bouy test --safety         # Dependency vulnerabilities
./bouy test --pip-audit      # Pip package audit

# Run all CI checks including security
./bouy test                  # Runs all tests and security checks

# Check specific files
./bouy test --bandit -- app/api/
```

### Pre-deployment Checklist

- [ ] Run full test suite: `./bouy test`
- [ ] Check for secrets: Review git diff for any hardcoded credentials
- [ ] Verify environment: Ensure `.env` is properly configured
- [ ] Review dependencies: Check for security updates
- [ ] Test in isolated environment: Use `./bouy up --test`
- [ ] Monitor logs: Check for any security warnings

## Branch Protection

The repository enforces branch protection rules:

- **Protected Branches**: `main` and `develop`
- **Required Checks**: All CI tests must pass
- **PR Reviews**: Required for `main` branch
- **No Force Pushes**: History is immutable
- **Automated Security Checks**: Run on every PR

## Contact

For security concerns:

1. **Security Vulnerabilities**: Use GitHub Security Advisories (private)
2. **General Security Questions**: Open a discussion in the repository
3. **Urgent Issues**: Contact repository maintainers directly via GitHub

Remember: **Never disclose security vulnerabilities publicly** until they have been addressed.