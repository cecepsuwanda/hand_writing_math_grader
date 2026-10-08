@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONIOENCODING=utf-8

REM Live smoke against Ollama (not for CI). Requires models in app\config\config.yaml.
REM Sample PDF: data\input\jawaban\smoke_inequality.pdf

echo Running live smoke: POST /api/process smoke_inequality.pdf
python scripts\smoke_live.py smoke_inequality.pdf smoke_001
exit /b %ERRORLEVEL%
