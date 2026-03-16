@echo off
echo ============================================
echo    Expo Mobile App Startup
echo ============================================
echo.

:: Work from the folder that contains this script.
cd /d "%~dp0"

:: Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed!
    pause
    exit /b 1
)

:: Check npm
call npm.cmd --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not installed!
    pause
    exit /b 1
)

:: Open the new Expo mobile app.
if exist "new front end\wardrobe-app\" (
    cd "new front end\wardrobe-app"
) else (
    echo [ERROR] Could not find folder "new front end\wardrobe-app"
    echo Current dir: %cd%
    pause
    exit /b 1
)

:: Install dependencies if needed.
if not exist "node_modules\" (
    echo [MISSING] node_modules not found. Installing...
    call npm.cmd install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
)

:: Expo should be present in the installed dependencies.
if not exist "node_modules\expo\" (
    echo [FIX] Expo package missing. Reinstalling dependencies...
    call npm.cmd install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
)

:: Export the backend URL so Expo Go uses the current LAN IP explicitly.
set "LOCAL_IP="
for /f "usebackq delims=" %%I in (`python -c "import re, subprocess; text=subprocess.check_output(['ipconfig'], encoding='utf-8', errors='ignore'); cur=''; candidates=[]; [candidates.append((cur, m.group(1))) for line in text.splitlines() for s in [line.strip()] for _ in [cur := s if s.endswith(':') and 'adapter' in s.lower() else cur] for m in [re.search(r'IPv4[^:]*:\s*([0-9.]+)', line)] if m]; preferred=next((ip for name, ip in candidates if re.search(r'Wireless LAN adapter|WLAN|Wi-Fi', name, re.I) and not ip.startswith('169.254.') and not ip.startswith('127.')), ''); preferred=preferred or next((ip for name, ip in candidates if not re.search(r'VMware|VirtualBox|Hyper-V|vEthernet|Nord|OpenVPN|TAP|Bluetooth|Loopback', name, re.I) and not ip.startswith('169.254.') and not ip.startswith('127.')), ''); print(preferred)" 2^>nul`) do set "LOCAL_IP=%%I"
if defined LOCAL_IP (
    set "EXPO_PUBLIC_API_BASE_URL=http://%LOCAL_IP%:8000"
    echo [OK] API base URL: %EXPO_PUBLIC_API_BASE_URL%
) else (
    echo [WARN] Could not detect a LAN IPv4 address.
    echo [WARN] Expo will fall back to runtime host detection.
)

echo.
echo [OK] Ready to start!
echo ============================================
echo    Starting Expo Dev Server...
echo    App folder: new front end\wardrobe-app
echo    Scan the QR code with Expo Go on your phone
echo ============================================
echo.

:: Start Expo and clear the Metro cache.
call npm.cmd run start -- --clear

:: Keep the window open after the server stops.
pause
