# Fixing psycopg2-binary Installation on Windows

## Problem
`psycopg2-binary` fails to install on Windows due to missing build tools or compilation issues.

## Solutions (Try in Order)

### Solution 1: Install Pre-built Wheel Directly (Easiest)

```powershell
# Try installing from a pre-built wheel
pip install psycopg2-binary==2.9.9 --only-binary :all:

# Or try a slightly older version that has better Windows support
pip install psycopg2-binary==2.9.8
```

### Solution 2: Install Visual C++ Build Tools

1. **Download Visual Studio Build Tools:**
   - Go to: https://visualstudio.microsoft.com/downloads/
   - Download "Build Tools for Visual Studio"
   - During installation, select "C++ build tools"

2. **Restart your terminal** and try again:
   ```powershell
   pip install -r requirement.txt
   ```

### Solution 3: Install psycopg2-binary Separately First

```powershell
# Install psycopg2-binary first (may take a few minutes)
pip install psycopg2-binary

# Then install the rest
pip install -r requirement.txt --no-deps
pip install -r requirement.txt
```

### Solution 4: Use Alternative - psycopg (Pure Python)

If `psycopg2-binary` continues to fail, you can use `psycopg` (pure Python, slower but works everywhere):

1. **Update requirement.txt** (temporarily):
   ```txt
   # Replace: psycopg2-binary==2.9.9
   # With: psycopg[binary]==3.1.18
   ```

2. **Update database URL** in `.env`:
   ```env
   # Change from:
   DATABASE_URL=postgresql+psycopg2://...
   # To:
   DATABASE_URL=postgresql+psycopg://...
   ```

3. **Update session.py** (if needed):
   ```python
   # Change connection string format if using psycopg3
   ```

### Solution 5: Use Conda/Miniconda (Alternative Package Manager)

```powershell
# Install Miniconda: https://docs.conda.io/en/latest/miniconda.html
# Then:
conda install -c conda-forge psycopg2
pip install -r requirement.txt
```

### Solution 6: Install Without psycopg2-binary (For Testing)

If you just want to test other parts of the app:

```powershell
# Create a temporary requirements file without psycopg2-binary
Get-Content requirement.txt | Where-Object { $_ -notmatch "psycopg2" } | Out-File requirement-temp.txt

# Install everything else
pip install -r requirement-temp.txt

# Note: Database features won't work until psycopg2 is installed
```

## Recommended Approach

**For most users, try Solution 1 first:**

```powershell
pip install psycopg2-binary==2.9.9 --only-binary :all:
pip install -r requirement.txt
```

If that fails, try Solution 3 (install separately first).

## Verification

After installation, verify it works:

```powershell
python -c "import psycopg2; print('psycopg2 installed successfully!')"
```

## If All Else Fails

1. **Use Docker for PostgreSQL** (recommended):
   ```powershell
   .\start_postgres_docker.ps1
   ```

2. **Use WSL2** (Windows Subsystem for Linux):
   - Install WSL2
   - Run pip install inside WSL2 (Linux has better package support)

3. **Contact Support** with:
   - Python version: `python --version`
   - pip version: `pip --version`
   - Full error message
