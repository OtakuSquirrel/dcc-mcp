@echo off
REM Create a junction so CodeBuddy can pick up the dcc-mcp-control skill
REM without physically copying files. A junction (/J) does NOT require
REM administrator privileges (unlike a /D symbolic link).
REM
REM Target: %USERPROFILE%\.codebuddy\skills\dcc-mcp-control
REM Source:  skills\dcc-mcp-control  (relative to this script)

setlocal EnableExtensions
cd /d "%~dp0"

set "SRC=%~dp0..\skills\dcc-mcp-control"
set "DST=%USERPROFILE%\.codebuddy\skills\dcc-mcp-control"

REM 1. Verify the source skill folder exists.
if not exist "%SRC%\" (
    echo [ERROR] Source folder not found: %SRC%
    goto :end
)

REM 2. Make sure the destination parent directory exists.
if not exist "%USERPROFILE%\.codebuddy\skills\" (
    echo Creating directory: %USERPROFILE%\.codebuddy\skills
    mkdir "%USERPROFILE%\.codebuddy\skills" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to create destination directory.
        goto :end
    )
)

REM 3. Remove any existing junction/folder at the destination first.
if exist "%DST%" (
    echo Removing existing target: %DST%
    rmdir /q "%DST%" >nul 2>&1
    if exist "%DST%" (
        echo [WARN] Target is a real directory; removing recursively...
        rmdir /s /q "%DST%" >nul 2>&1
    )
    if exist "%DST%" (
        echo [ERROR] Could not remove existing target.
        goto :end
    )
)

REM 4. Create the junction.
echo Creating junction:
echo   from: %SRC%
echo   to:   %DST%
mklink /J "%DST%" "%SRC%"

if errorlevel 1 (
    echo [ERROR] Failed to create junction. Try running from a normal prompt.
) else (
    echo [OK] Junction created. Restart CodeBuddy to load the skill.
)

:end
echo.
pause
