# Commercial Edition Distribution Guide

> `docmirror-enterprise` and `docmirror-finance` are **not** published on public PyPI.
> **Both packages follow the same distribution model** described below.
> Paid customers receive access via a private index or direct `.whl` files.

## Option 1: Private PyPI Index (Recommended)

### Server Setup

Use `pypiserver` — a minimal single-file PyPI server:

```bash
# On an internal server (e.g., enterprise-pypi.valuemapglobal.com)
pip install pypiserver passlib

# Create user credentials
htpasswd -c /opt/pypiserver/.htpasswd customer1

# Start (use systemd / supervisor for production)
pypiserver run \
  -p 8080 \
  -P /opt/pypiserver/.htpasswd \
  /opt/pypiserver/packages/
```

### Build & Upload

```bash
# Build the enterprise/finance package in CI/CD
cd docmirror-enterprise/
python -m build
# → dist/docmirror_enterprise-0.4.0-py3-none-any.whl

pip install twine
twine upload \
  --repository-url https://enterprise-pypi.valuemapglobal.com:8080/ \
  -u customer1 -p $PASSWORD \
  dist/*.whl
```

### Customer Installation

Depending on the tier purchased:

```bash
# Enterprise customer
pip install docmirror-enterprise \
  --extra-index-url https://enterprise-pypi.valuemapglobal.com:8080/ \
  --trusted-host enterprise-pypi.valuemapglobal.com

# Finance customer (includes all enterprise features)
pip install docmirror-finance \
  --extra-index-url https://enterprise-pypi.valuemapglobal.com:8080/ \
  --trusted-host enterprise-pypi.valuemapglobal.com
```

## Option 2: Direct `.whl` Distribution

Suitable for a small number of customers or air-gapped environments.

```bash
# Build
cd docmirror-enterprise/
python -m build
# → dist/docmirror_enterprise-0.4.0-py3-none-any.whl

# Send via email, internal file share, or customer portal

# Customer installs
pip install docmirror_enterprise-0.4.0-py3-none-any.whl
```

## Option 3: GitHub Packages (Zero Extra Cost)

Use GitHub Packages from a **private** repository.

```yaml
# .github/workflows/publish-enterprise.yml
- name: Publish enterprise to GitHub Packages
  run: |
    pip install twine
    twine upload \
      --repository-url https://upload.pypi.org/legacy/ \
      dist/*.whl
```

> **Important**: The repository **must be private**. Public repositories make packages visible to everyone.

## License File

After installing the commercial package, a `.lic` license file is required:

```bash
# Customer downloads the .lic file from the license portal or email
mkdir -p ~/.docmirror/licenses
cp license.lic ~/.docmirror/licenses/

# Verify installation
python -c "
from docmirror.plugins._runtime.licensing.offline import offline_license_manager
print(f'License status: {len(offline_license_manager._licenses)} license(s) loaded')
"
```
