@echo off
echo ============================================
echo    Backend Server Startup
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)
echo [OK] Python is installed

:: Check and install required packages
echo.
echo Checking required Python packages...
echo.

:: Check each required package
pip show langchain-google-genai >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] langchain-google-genai - Installing...
    pip install langchain-google-genai
)

pip show langchain-openai >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] langchain-openai - Installing...
    pip install langchain-openai
)

pip show langgraph >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] langgraph - Installing...
    pip install langgraph
)

pip show python-dotenv >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] python-dotenv - Installing...
    pip install python-dotenv
)

pip show requests >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] requests - Installing...
    pip install requests
)

pip show fastapi >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] fastapi - Installing...
    pip install fastapi
)

pip show uvicorn >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] uvicorn - Installing...
    pip install "uvicorn[standard]"
)

pip show Pillow >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] Pillow - Installing...
    pip install Pillow
)

pip show python-multipart >nul 2>&1
if %errorlevel% neq 0 (
    echo [MISSING] python-multipart - Installing...
    pip install python-multipart
)

echo.
echo [OK] All required packages are installed!
echo.
echo ============================================
echo    Starting Backend Server...
echo    URL: http://localhost:8000
echo ============================================
echo.

python server.py
pause
