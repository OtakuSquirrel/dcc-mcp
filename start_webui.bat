@echo off
title dcc-mcp Dashboard
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set PYTHON=.venv\Scripts\python.exe
) else (
    set PYTHON=python
)

set PORT=8420

echo.
echo  dcc-mcp Dashboard
echo  http://127.0.0.1:%PORT%
echo  Close this window to stop the server.
echo.

start "" http://127.0.0.1:%PORT%
%PYTHON% -m dcc_mcp_core.webui --port %PORT%
