@echo off
title dcc-mcp Dashboard
cd /d "%~dp0"

:: Try project venv first, then system Python
if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

set PORT=8420
echo.
echo  dcc-mcp Dashboard
echo  http://127.0.0.1:%PORT%
echo.

:: Open browser after a short delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:%PORT%"

:: Start the server (blocks until Ctrl+C)
%PYTHON% -m dcc_mcp_core.webui --port %PORT%
