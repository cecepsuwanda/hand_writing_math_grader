@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8

REM Live smoke against Ollama (not for CI). Requires models in app\config\config.yaml.
REM Sample PDF: data\input\jawaban\smoke_inequality.pdf

echo Running live smoke: process smoke_inequality.pdf
python -m app.cli process smoke_inequality.pdf --student-id smoke_001
exit /b %ERRORLEVEL%
