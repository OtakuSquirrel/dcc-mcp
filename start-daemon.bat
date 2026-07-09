@echo off
REM Start the dcc-mcp daemon in THIS terminal window.
REM   - The window stays open while the daemon runs.
REM   - All logs stream here live.
REM   - Close the window (or Ctrl-C) to stop the daemon.
REM
REM Double-click this file, or run it from a terminal.

cd /d "%~dp0"
title dcc-daemon (close window to stop)
echo ============================================================
echo   dcc-daemon starting
echo   MCP:      http://127.0.0.1:8765/mcp   (agents connect here)
echo   Dashboard http://127.0.0.1:8765/      (open in a browser)
echo   Register: 127.0.0.1:8766              (DCCs dial in here)
echo.
echo   Close this window or press Ctrl-C to STOP the daemon.
echo ============================================================
echo.

".venv\Scripts\dcc-daemon.exe" --log-level INFO

echo.
echo daemon stopped. Press any key to close.
pause >nul
