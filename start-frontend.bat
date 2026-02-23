@echo off
echo ============================================
echo    Frontend Server Startup
echo ============================================
echo.

:: 1. 設定工作目錄為此 .bat 檔案所在位置 (避免路徑錯誤)
cd /d "%~dp0"

:: Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed!
    pause
    exit /b 1
)

:: Check npm
call npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm is not installed!
    pause
    exit /b 1
)

:: 2. 進入前端資料夾 (增加錯誤檢查)
if exist "front end\my-fashion-app\" (
    cd "front end\my-fashion-app"
) else (
    echo [ERROR] Could not find folder "front end\my-fashion-app"
    echo Current dir: %cd%
    pause
    exit /b 1
)

:: 3. 檢查並安裝依賴 (使用 call 避免腳本中斷)
if not exist "node_modules\" (
    echo [MISSING] node_modules not found. Installing...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
)

:: 4. 快速檢查關鍵套件 (若缺漏則補安裝)
if not exist "node_modules\vite\" (
    echo [FIX] Vite missing. Updating dependencies...
    call npm install
)

echo.
echo [OK] Ready to start!
echo ============================================
echo    Starting Frontend Dev Server...
echo    URL: http://localhost:5173
echo ============================================
echo.

:: 5. 啟動伺服器 (使用 call)
call npm run dev

:: 伺服器關閉後暫停，讓你看到錯誤訊息
pause