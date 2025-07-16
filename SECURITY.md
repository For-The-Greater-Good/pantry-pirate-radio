# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Which versions are eligible for receiving such patches depends on the CVSS v3.0 Rating:

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities to the maintainers by opening a security advisory on GitHub:

1. Go to the Security tab
2. Click on "Report a vulnerability"
3. Fill out the form with details about the vulnerability

### What to Include

- Type of issue (e.g., buffer overflow, SQL injection, cross-site scripting, etc.)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit the issue

### Response Timeline

- We will acknowledge receipt of your vulnerability report within 48 hours
- We will provide an initial assessment within 7 days
- We will work on fixes and coordinate disclosure timelines with you

## Security Best Practices

### For Contributors

1. **Never commit secrets**: API keys, passwords, or tokens should never be committed
2. **Use environment variables**: All sensitive configuration should come from environment
3. **Follow secure coding practices**: Input validation, output encoding, proper authentication
4. **Keep dependencies updated**: Regularly update dependencies to patch known vulnerabilities

### For Users

1. **Use strong passwords**: For database and other service credentials
2. **Rotate secrets regularly**: Change API keys and passwords periodically
3. **Use environment-specific credentials**: Don't reuse credentials between environments
4. **Monitor logs**: Check application logs for suspicious activity

## Security Features

This application implements several security measures:

- **Input validation**: All user inputs are validated and sanitized
- **SQL injection prevention**: Uses parameterized queries via SQLAlchemy
- **Rate limiting**: API endpoints are rate-limited to prevent abuse
- **Security headers**: Implements security headers for API responses
- **Dependency scanning**: Regular security scans via GitHub Dependabot
- **Secret scanning**: GitHub secret scanning is enabled
- **Code analysis**: Bandit security linter in CI pipeline

## Known Security Considerations

- This is a public data aggregation service - no authentication is required by design
- All data served is public information about food resources
- No personal or sensitive user data is collected or stored
- API is read-only for public access

## Contact

For any security concerns, please contact the maintainers through GitHub security advisories.