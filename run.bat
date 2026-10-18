@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM Starts the local web UI (default http://127.0.0.1:8000, see web: in config.yaml).
REM Examples:
REM   run.bat
REM   run.bat --port 8765
REM   run.bat --config path\to\config.yaml

set "PORT=8000"
set "PREV="
for %%A in (%*) do (
  if /I "!PREV!"=="--port" set "PORT=%%A"
  set "PREV=%%A"
)

REM Free a leftover listener on the same loopback port (common after a prior run.bat).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%PORT%;" ^
  "$conns=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -eq '127.0.0.1' -or $_.LocalAddress -eq '::1' });" ^
  "if ($conns.Count -eq 0) { exit 0 };" ^
  "$pids=@($conns | Select-Object -ExpandProperty OwningProcess -Unique);" ^
  "foreach ($procId in $pids) {" ^
  "  $p=Get-Process -Id $procId -ErrorAction SilentlyContinue;" ^
  "  if ($null -eq $p) { continue };" ^
  "  Write-Host ('Stopping leftover ' + $p.ProcessName + ' (PID ' + $procId + ') on port ' + $port + '...');" ^
  "  Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue;" ^
  "}" ^
  "Start-Sleep -Milliseconds 800"

python -m app.web %*
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo ERROR: server exited with code %EXITCODE%.
  echo If the port is busy, close the other Math Grader window or run: run.bat --port 8765
)
exit /b %EXITCODE%
