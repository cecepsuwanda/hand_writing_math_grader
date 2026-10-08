@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM Starts the local web UI (default http://127.0.0.1:8000, see web: in config.yaml).
REM Examples:
REM   run.bat
REM   run.bat --port 8765
REM   run.bat --config path\to\config.yaml

python -m app.web %*

set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo ERROR: server exited with code %EXITCODE%.
)
exit /b %EXITCODE%
