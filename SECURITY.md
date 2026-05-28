# Security Policy

## Overview
This project follows security best practices to protect sensitive data and credentials.

## Environment Variables & Secrets

### ⚠️ Never commit secrets to this repository
Sensitive data such as API keys, database passwords, and Django secret keys must **never** be committed to git.

### Configuration: Using `.env` Files

1. **Local Development**:
   - Create a `.env` file in the project root (automatically ignored by `.gitignore`)
   - Copy template from `.env.example` and fill with your local values
   - See `interview_ai/settings.py` for all supported environment variables

2. **Production/Deployment**:
   - Set environment variables in your hosting platform:
     - GitHub Actions: Use repository Secrets (Settings → Secrets)
     - Docker/Kubernetes: Use ConfigMaps or Secrets
     - Heroku/Cloud Platforms: Use their native secret management
     - CI/CD pipelines: Use platform-specific secret storage

### Required Environment Variables

```bash
# Django Configuration
SECRET_KEY=<generate-new-secret>  # REQUIRED for production

# Email Configuration (Gmail SMTP)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=<app-specific-password>

# AI Services
GROQ_API_KEY=<your-groq-key>

# Optional
DEBUG=False  # Set to False in production
```

### Generating a New SECRET_KEY

If you need to generate a new Django secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Incident Response: Exposed Secret

If you accidentally commit a secret:

1. **Immediate**: Rotate/revoke the exposed credential
2. **Code**: Move secret to environment variable in code
3. **Commit**: Commit the code change
4. **History**: Use `git filter-branch` or `git-filter-repo` to remove from history
5. **Force Push**: `git push origin main --force` (coordinate with team)
6. **Verify**: Confirm no traces remain: `grep -r "secret-value" .`

## Recent Security Updates

- **Date**: 2026-05-28
- **Change**: Moved hardcoded `SECRET_KEY` to environment variable
- **Impact**: All deployments must now set `SECRET_KEY` in their environment
- **History**: Forced push to GitHub removed old commits with exposed key

## Best Practices

- ✅ Use environment variables for all secrets
- ✅ Add secret names (not values!) to `.env.example`  
- ✅ Review `.gitignore` before commits
- ✅ Use a secret scanner in CI/CD (e.g., `truffleHog`, `detect-secrets`)
- ✅ Rotate secrets regularly in production
- ❌ Never use hardcoded keys, passwords, or tokens
- ❌ Never commit `.env` files
- ❌ Never commit private keys or certificates

## Questions or Issues?

If you discover a security vulnerability, please **do not** open a public issue. 
Contact the maintainers privately at: [security contact information]
