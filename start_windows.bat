@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto path_error

echo =====================================
echo   LandLex - Local Startup (Windows)
echo =====================================
echo.

if not exist ".env" (
    if not exist ".env.example" goto files_missing
    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 goto files_missing
    echo [INFO] Created .env. Set ADMIN_TOKEN before using admin features.
)

if exist ".venv\Scripts\python.exe" goto install

echo [1/3] Checking Python 3.11 or newer...
set "PYRUN="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYRUN=py -3"
)
if defined PYRUN goto create_env
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYRUN=python"
)
if not defined PYRUN goto no_python

:create_env
echo [INFO] Creating a Python virtual environment...
%PYRUN% -m venv ".venv"
if errorlevel 1 goto venv_error
if not exist ".venv\Scripts\python.exe" goto venv_error

:install
echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto install_error

echo [3/3] Starting LandLex server...
echo URL: http://127.0.0.1:8000
echo Keep this terminal window open while using LandLex.
echo.
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto server_error
exit /b 0

:no_python
echo.
echo [ERROR] Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo During setup, enable "Add python.exe to PATH" if offered.
echo Then close and reopen this terminal, and run this file again.
pause
exit /b 1

:venv_error
echo [ERROR] Failed to create .venv. Check your Python installation.
echo You can run: py -3 --version
pause
exit /b 1

:install_error
echo [ERROR] Python package installation failed.
echo Check the message above and your internet connection.
pause
exit /b 1

:server_error
echo [ERROR] Server stopped unexpectedly. Check the message above.
pause
exit /b 1

:path_error
echo [ERROR] Could not open the project folder.
pause
exit /b 1

:files_missing
echo [ERROR] Missing .env.example or cannot create .env.
echo Ensure you extracted the entire ZIP before running this file.
pause
exit /b 1
