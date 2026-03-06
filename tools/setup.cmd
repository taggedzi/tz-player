@echo off
setlocal enabledelayedexpansion

set "repo_root=%~dp0.."
set "setup_cmd=setup"

set "venv_python=%repo_root%\.venv\Scripts\python.exe"
if exist "%venv_python%" (
  "%venv_python%" -m tz_player.app %setup_cmd% %*
  exit /b %errorlevel%
)

set "ubuntu_venv=%repo_root%\.ubuntu-venv\Scripts\python.exe"
if exist "%ubuntu_venv%" (
  "%ubuntu_venv%" -m tz_player.app %setup_cmd% %*
  exit /b %errorlevel%
)

where tz-player >nul 2>&1
if %errorlevel%==0 (
  tz-player %setup_cmd% %*
  exit /b %errorlevel%
)

where python >nul 2>&1
if %errorlevel%==0 (
  python -m tz_player.app %setup_cmd% %*
  exit /b %errorlevel%
)

where python3 >nul 2>&1
if %errorlevel%==0 (
  python3 -m tz_player.app %setup_cmd% %*
  exit /b %errorlevel%
)

echo ERROR: No Python interpreter found (expected python or python3). 1>&2
exit /b 127
