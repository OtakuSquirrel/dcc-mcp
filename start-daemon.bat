@echo off
REM Restart this checkout's dcc-mcp daemon in THIS terminal window.
REM   - The window stays open while the daemon runs.
REM   - All logs stream here live.
REM   - Close the window (or Ctrl-C) to stop the daemon.
REM
REM Double-click this file, or run it from a terminal.

setlocal
cd /d "%~dp0" || goto :failed
title dcc-mcp (close window to stop)
echo ============================================================
echo   dcc-mcp restarting
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv. Run uv sync --extra dev first.
    goto :failed
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\restart-daemon.ps1"
if errorlevel 1 goto :failed

echo   Close this window or press Ctrl-C to STOP the daemon.
echo.
"%~dp0.venv\Scripts\python.exe" -m dcc_mcp --log-level INFO
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo dcc-mcp could not start. See the error above. Press any key to close.
pause >nul
exit /b 1
