@echo off
setlocal
cd /d "%~dp0"
title LandLex Upload to GitHub

echo ==============================================
echo LandLex GitHub Upload (sedama85/landlex)
echo ==============================================
echo.
echo [NOTICE] Create an EMPTY repository first:
echo https://github.com/new
echo Repository name: landlex

echo.
where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not in PATH.
  echo Download from https://git-scm.com/downloads/win
  pause
  exit /b 1
)

if exist ".env" (
  echo [WARNING] .env exists. It is excluded by .gitignore.
)

if not exist ".git" (
  git init
  if errorlevel 1 goto failed
)
git branch -M main
if errorlevel 1 goto failed

git add app static tests .gitignore .env.example requirements.txt Dockerfile docker-compose.yml render.yaml README.md FREE_AI_SETUP.txt PUBLIC_BETA_DEPLOY.md run.sh start_windows.bat upload_to_github_windows.bat pytest.ini
if errorlevel 1 goto failed

echo.
echo Staged files (check that no secrets are listed):
git diff --cached --name-only

echo.
echo If you see .env, API keys, or private PDFs above, close this window now.
set /p CONTINUE=Continue upload? [Y/N]: 
if /I not "%CONTINUE%"=="Y" (
  echo Cancelled.
  pause
  exit /b 0
)

git -c user.name="LandLex" -c user.email="233654237+sedama85@users.noreply.github.com" commit -m "Publish LandLex public beta"
if errorlevel 1 (
  echo [INFO] No new commit created or commit failed.
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/sedama85/landlex.git
  if errorlevel 1 goto failed
)
echo.
echo Uploading to GitHub. GitHub login may open in your browser.
git push -u origin main
if errorlevel 1 goto failed

echo.
echo [SUCCESS] https://github.com/sedama85/landlex
echo Now open https://dashboard.render.com/ and create a Blueprint.
pause
exit /b 0

:failed
echo.
echo [ERROR] Upload failed. Copy the error message to ChatGPT.
pause
exit /b 1
