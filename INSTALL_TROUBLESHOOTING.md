# Installation Troubleshooting Guide

## Common Issues and Solutions

### Issue 1: Version Not Available

If `pydantic==2.6.4` is not available, try:

```powershell
# Check available versions
pip index versions pydantic

# Install latest compatible version
pip install pydantic pydantic-settings
```

### Issue 2: Dependency Conflicts

Try installing in order:

```powershell
# 1. Install pydantic first
pip install pydantic

# 2. Then install pydantic-settings
pip install pydantic-settings

# 3. Then pin versions if needed
pip install pydantic==2.6.4 pydantic-settings==2.2.1
```

### Issue 3: Network/Proxy Issues

```powershell
# Use trusted hosts
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pydantic pydantic-settings

# Or increase timeout
pip install --default-timeout=100 pydantic pydantic-settings
```

### Issue 4: Try Latest Versions

```powershell
# Install latest versions (may be more compatible)
pip install pydantic pydantic-settings

# Then check what was installed
pip show pydantic pydantic-settings
```

### Issue 5: Install Without Version Constraints

Update requirement.txt temporarily to use flexible versions:

```txt
# Instead of:
pydantic==2.6.4
pydantic-settings==2.2.1

# Try:
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0
```

### Issue 6: Clear Cache and Retry

```powershell
# Clear pip cache
pip cache purge

# Upgrade pip first
python -m pip install --upgrade pip

# Then install
pip install pydantic pydantic-settings
```

### Issue 7: Check Python Version Compatibility

```powershell
# Check Python version
python --version

# pydantic 2.6.4 requires Python 3.8+
# If Python < 3.8, you need to upgrade Python
```

## Step-by-Step Debugging

1. **Check what's installed:**
   ```powershell
   pip list | findstr pydantic
   ```

2. **Check what's available:**
   ```powershell
   pip index versions pydantic
   pip index versions pydantic-settings
   ```

3. **Try minimal install:**
   ```powershell
   pip install pydantic
   # If that works, then:
   pip install pydantic-settings
   ```

4. **Check for conflicts:**
   ```powershell
   pip check
   ```

5. **Install with verbose output:**
   ```powershell
   pip install -v pydantic pydantic-settings
   ```

## Alternative: Update requirement.txt

If specific versions aren't available, update requirement.txt to be more flexible:

```txt
# Flexible version ranges
pydantic>=2.6.0,<3.0.0
pydantic-settings>=2.2.0,<3.0.0
```

This allows pip to install compatible versions that are actually available.
