@echo off
setlocal enabledelayedexpansion

set "repo_root=%~dp0.."
set "release_py=%~dp0release.py"

if not exist "%release_py%" (
  echo ERROR: Missing helper script: %release_py% 1>&2
  exit /b 1
)

set "venv_python=%repo_root%\.ubuntu-venv\Scripts\python.exe"
if exist "%venv_python%" (
  "%venv_python%" "%release_py%" %*
  exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
  python "%release_py%" %*
  exit /b %errorlevel%
)

where python3 >nul 2>&1
if %errorlevel%==0 (
  python3 "%release_py%" %*
  exit /b %errorlevel%
)

echo ERROR: No Python interpreter found (expected python or python3). 1>&2
exit /b 127
