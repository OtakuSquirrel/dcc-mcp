@echo off
REM ==========================================================================
REM  DCC MCP Manager — Windows one-click dev launcher
REM
REM  Sets up the MSVC Build Tools environment (vcvars64), puts cargo on PATH,
REM  cd into tauri-manager/, and runs `npm run tauri dev`.
REM
REM  Double-click this file to start the manager. Close the console window
REM  (or Ctrl+C inside it) to stop the app.
REM ==========================================================================
setlocal

echo [start-manager] locating Visual Studio Build Tools ...

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_vswhere

REM Query vswhere for any VS install that has the x86/x64 C++ tools.
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS_PATH=%%i"
if not defined VS_PATH goto :no_vs

set "VCVARS=%VS_PATH%\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS%" goto :no_vcvars

echo [start-manager] found: %VS_PATH%

REM Put cargo and the VS Installer dir (where vswhere lives) on PATH.
REM vcvars64 internally shells out to vswhere; without this it prints
REM a harmless but noisy "not recognized" warning.
set "PATH=%USERPROFILE%\.cargo\bin;%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"

REM Source MSVC build env into this shell (quietly).
call "%VCVARS%" > nul

REM cd into the Tauri manager project (this file lives at repo root).
cd /d "%~dp0tauri-manager"

echo [start-manager] starting `npm run tauri dev` ...
echo.
call npm run tauri dev
goto :end


REM --------------------------------------------------------------------------
REM  Error paths
REM --------------------------------------------------------------------------
:no_vswhere
echo.
echo [start-manager] ERROR: vswhere.exe not found.
echo   Install Visual Studio Build Tools 2022 with the C++ workload via:
echo     winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
goto :fail

:no_vs
echo.
echo [start-manager] ERROR: no Visual Studio install with C++ tools found.
echo   Install the VCTools workload via Visual Studio Installer.
goto :fail

:no_vcvars
echo.
echo [start-manager] ERROR: vcvars64.bat missing at "%VCVARS%"
echo   Your VS install looks incomplete. Repair it via Visual Studio Installer.
goto :fail


:fail
echo.
pause
exit /b 1

:end
echo.
echo [start-manager] manager stopped. press any key to close.
pause > nul
endlocal
