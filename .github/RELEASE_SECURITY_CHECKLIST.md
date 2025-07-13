# Release Security Checklist

Use this checklist before every release to ensure security standards are met.

## Pre-Release Security Review

### Code Security
- [ ] All security scanning tools pass (Bandit, Safety, pip-audit)
- [ ] CodeQL analysis shows no critical security issues
- [ ] No secrets or API keys in code or configuration
- [ ] All dependencies are up to date
- [ ] No high-severity vulnerabilities in dependencies

### Data Security
- [ ] No real PII in test data files
- [ ] All test phone numbers use 555-xxx-xxxx format
- [ ] All test emails use example.com/test.com domains
- [ ] No real addresses in test data
- [ ] Data files are properly anonymized

### Configuration Security
- [ ] `.env.example` contains only placeholder values
- [ ] No hardcoded credentials in configuration files
- [ ] All environment variables are properly documented
- [ ] Database passwords use strong defaults in examples
- [ ] No internal URLs or IP addresses exposed

### Git History Security
- [ ] No secrets in Git history (run `git log --all -p | grep -i "password\|secret\|key"`)
- [ ] No `.env` files committed (run `git log --all --name-only | grep "\.env$"`)
- [ ] No sensitive files in repository
- [ ] All commits follow security guidelines

### Documentation Security
- [ ] Security documentation is up to date
- [ ] Vulnerability disclosure process is documented
- [ ] Contributing guidelines include security requirements
- [ ] Installation instructions emphasize security best practices

### Infrastructure Security
- [ ] Docker images use non-root users
- [ ] Container security scanning passes
- [ ] No exposed ports in production configuration
- [ ] Database connections use strong authentication

## Release Process Security

### Before Tagging
- [ ] Run full security scan: `poetry run bandit -r app/`
- [ ] Check for PII: Review all CSV/JSON files manually
- [ ] Verify pre-commit hooks are working
- [ ] Test security workflows in CI/CD

### During Release
- [ ] Use signed commits for release tags
- [ ] Verify release artifacts don't contain secrets
- [ ] Double-check Docker image security
- [ ] Review release notes for security impact

### After Release
- [ ] Monitor for security issues in the first 24 hours
- [ ] Verify security scanning continues to pass
- [ ] Check that no secrets were accidentally exposed
- [ ] Update security documentation if needed

## Emergency Security Response

If a security issue is discovered after release:

1. **Immediate Response (< 1 hour)**
   - [ ] Assess the severity and scope
   - [ ] Determine if immediate action is needed
   - [ ] Notify key stakeholders privately

2. **Short-term Response (< 24 hours)**
   - [ ] Develop and test a fix
   - [ ] Prepare security advisory
   - [ ] Plan coordinated disclosure

3. **Long-term Response (< 1 week)**
   - [ ] Release patched version
   - [ ] Publish security advisory
   - [ ] Update security documentation
   - [ ] Review and improve security processes

## Security Contacts

- **Primary**: Repository maintainers via GitHub private message
- **Security Issues**: Create private security advisory on GitHub
- **Emergency**: Follow vulnerability disclosure process in SECURITY.md

## Security Metrics

Track these metrics for each release:
- [ ] Number of security issues found and fixed
- [ ] Time to fix critical security issues
- [ ] Number of dependency vulnerabilities
- [ ] Security scan coverage percentage
- [ ] Number of false positives in security scans

## Post-Release Security Monitoring

After each release:
- [ ] Monitor GitHub security alerts
- [ ] Watch for new CVEs affecting dependencies
- [ ] Review security scan results regularly
- [ ] Update security documentation as needed
- [ ] Plan security improvements for next release

---

**Release Manager**: ___________________ **Date**: ___________

**Security Reviewer**: ___________________ **Date**: ___________

**Final Approval**: ___________________ **Date**: ___________