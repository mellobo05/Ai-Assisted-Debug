# Network Error Analysis - Gemini API Connection

## Error Details

**Error Type:** `ServiceUnavailable` / `RetryError`

**Error Message:**
```
503 failed to connect to all addresses; last error: UNKNOWN: ipv4:142.250.206.10:443: tcp handshaker shutdown
```

**Error Code:** TCP connection error 10035 (WSAEWOULDBLOCK)

## Root Cause Analysis

### What's Happening:
1. ✅ **DNS Resolution:** Works - can resolve `generativelanguage.googleapis.com`
2. ❌ **TCP Connection:** Fails - cannot establish TCP connection to port 443
3. ❌ **HTTPS Connection:** Times out - connection handshake is being shut down
4. ❌ **gRPC Connection:** Fails - cannot connect to Google's API servers

### The Problem:
The TCP handshake is being **shut down** before it can complete. This indicates:
- **Firewall blocking** the connection
- **VPN blocking** Google services
- **Network security software** interfering
- **Corporate proxy/firewall** blocking outbound connections

## Troubleshooting Steps

### Step 1: Check Windows Firewall
```powershell
# Check firewall status
Get-NetFirewallProfile | Select-Object Name, Enabled

# Temporarily disable firewall to test (re-enable after!)
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
```

### Step 2: Check VPN Status
```powershell
# List network adapters
Get-NetAdapter | Select-Object Name, Status, InterfaceDescription

# Check for VPN adapters
Get-NetAdapter | Where-Object {$_.InterfaceDescription -like "*VPN*" -or $_.InterfaceDescription -like "*TAP*"}
```

**If VPN is active:**
- Try disconnecting VPN temporarily
- Configure VPN to allow Google services
- Add exception for `*.googleapis.com`

### Step 3: Check Proxy Settings
```powershell
# Check system proxy
netsh winhttp show proxy

# Check environment variables
$env:HTTP_PROXY
$env:HTTPS_PROXY
```

### Step 4: Test Direct Connection
```powershell
# Test HTTPS connection
Test-NetConnection -ComputerName generativelanguage.googleapis.com -Port 443

# Test with curl
curl -v https://generativelanguage.googleapis.com
```

### Step 5: Check Antivirus/Security Software
- Temporarily disable antivirus/firewall software
- Check if any security software is blocking Python/network connections
- Add Python to firewall exceptions

### Step 6: Try Different Network
- Connect to a different network (mobile hotspot, different WiFi)
- Test if the issue persists

## Solutions

### Solution 1: Configure Firewall Exception
```powershell
# Allow Python through firewall
New-NetFirewallRule -DisplayName "Python - Gemini API" -Direction Outbound -Program "C:\Users\lobomela\AppData\Local\Microsoft\WindowsApps\python.exe" -Action Allow
```

### Solution 2: Configure VPN Exception
If using VPN:
1. Open VPN settings
2. Add `*.googleapis.com` to allowed/whitelist
3. Or configure split tunneling to exclude Google services

### Solution 3: Use Proxy (if behind corporate firewall)
```powershell
# Set proxy if needed
$env:HTTPS_PROXY = "http://proxy.company.com:8080"
```

### Solution 4: Use Mock Embeddings (Temporary)
While fixing network issues, use mock embeddings:
```powershell
$env:USE_MOCK_EMBEDDING = "true"
python run_rag.py
```

### Solution 5: Test API Key Validity
Verify your API key works from a different network:
- Visit: https://aistudio.google.com/apikey
- Test the key from a browser or different network

## Quick Test Commands

```powershell
# Test 1: DNS Resolution
nslookup generativelanguage.googleapis.com

# Test 2: TCP Connection
Test-NetConnection -ComputerName generativelanguage.googleapis.com -Port 443

# Test 3: HTTPS Connection
Invoke-WebRequest -Uri "https://generativelanguage.googleapis.com" -TimeoutSec 10

# Test 4: Check if Python can make outbound connections
python -c "import socket; s = socket.socket(); s.connect(('google.com', 80)); print('OK')"
```

## Expected Behavior

**If network is working:**
- DNS resolves successfully ✅
- TCP connection succeeds ✅
- HTTPS connection returns 200/403/404 (not timeout) ✅
- Gemini API call succeeds ✅

**Current Status:**
- DNS resolves ✅
- TCP connection fails ❌
- HTTPS times out ❌
- Gemini API fails ❌

## Next Steps

1. **Disable VPN temporarily** and test
2. **Check Windows Firewall** settings
3. **Test from different network** (mobile hotspot)
4. **Use mock embeddings** for development while fixing network
5. **Contact network admin** if on corporate network
