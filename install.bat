@echo off
setlocal
cd /d "%~dp0"

echo Installing dependencies from requirements.txt ...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo ERROR: Python/pip not found. Install Python 3 and ensure it is on PATH.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: Failed to install requirements.
  pause
  exit /b 1
)

echo.
echo Done. Dependencies installed.
pause
exit /b 0
