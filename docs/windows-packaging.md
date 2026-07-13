# Windows packaging

The first distributable target is a self-contained Windows x64 `onedir`
build. End users do not need Python or uv.

## Build

Stop any development daemon that is running from `.venv`, then prepare the
build environment once:

```powershell
uv sync --extra dev
```

Build, validate the bundled plugin payloads, run an isolated-port smoke test,
and create the zip:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-portable.ps1
```

Output:

```text
artifacts/DCC-MCP-Portable-x64/
artifacts/DCC-MCP-Portable-x64.zip
```

The smoke test starts the frozen executable on two temporary free ports,
checks the diagnostics endpoint and four MCP tools, and then stops only that
test process. It can be skipped while iterating with `-SkipSmokeTest`.

## Why `onedir`

`onedir` starts without extracting the Python runtime into a temporary folder,
is easier to diagnose, and generally causes fewer antivirus false positives
than a PyInstaller `onefile` executable. The later Inno Setup phase will still
deliver a single user-facing installer executable.
