@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM Default: interactive process (choose PDF from data\input\jawaban)
REM Examples:
REM   run.bat
REM   run.bat process smoke_inequality.pdf
REM   run.bat render smoke_inequality.pdf
REM   run.bat --help

if "%~1"=="" (
  python -m app.cli process
) else (
  python -m app.cli %*
)

set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo ERROR: command exited with code %EXITCODE%.
  pause
)
exit /b %EXITCODE%
