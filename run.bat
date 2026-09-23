@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM Default: interactive main menu (ingest kunci / process PDF / exit)
REM Examples:
REM   run.bat
REM   run.bat menu
REM   run.bat ingest-kunci
REM   run.bat process
REM   run.bat process smoke_inequality.pdf
REM   run.bat render smoke_inequality.pdf
REM   run.bat --help

if "%~1"=="" (
  python -m app.cli menu
) else (
  python -m app.cli %*
)

set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo ERROR: command exited with code %EXITCODE%.
)
exit /b %EXITCODE%
