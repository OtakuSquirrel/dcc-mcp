param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "The Windows portable build must run on Windows."
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ArtifactsRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot "artifacts"))
$WorkRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot "build\pyinstaller"))
foreach ($Path in @($ArtifactsRoot, $WorkRoot)) {
    if (-not $Path.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Build output escaped the repository root: $Path"
    }
}

$PyInstaller = Join-Path $RepoRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path -LiteralPath $PyInstaller)) {
    throw "PyInstaller is missing. Run 'uv sync --extra dev' after stopping any running development daemon."
}

New-Item -ItemType Directory -Force -Path $ArtifactsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null
$PortableRoot = Join-Path $ArtifactsRoot "DCC-MCP-Portable-x64"
$ZipPath = Join-Path $ArtifactsRoot "DCC-MCP-Portable-x64.zip"
foreach ($Target in @($PortableRoot, $ZipPath)) {
    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
}

& $PyInstaller `
    --noconfirm `
    --clean `
    --distpath $ArtifactsRoot `
    --workpath $WorkRoot `
    (Join-Path $RepoRoot "packaging\windows\dcc-mcp.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

Copy-Item -LiteralPath (Join-Path $RepoRoot "packaging\windows\PORTABLE-README.txt") `
    -Destination (Join-Path $PortableRoot "README.txt")

foreach ($Required in @(
    "dcc-mcp.exe",
    "_internal\dcc_mcp\installers\payloads\common\dcc_socket_server.py",
    "_internal\dcc_mcp\installers\payloads\blender_daemon\__init__.py",
    "_internal\dcc_mcp\installers\payloads\houdini_daemon\__init__.py",
    "_internal\dcc_mcp\installers\payloads\maya_daemon\__init__.py",
    "_internal\dcc_mcp\installers\payloads\ue_daemon\__init__.py"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $PortableRoot $Required))) {
        throw "Portable artifact is missing required file: $Required"
    }
}

if (-not $SkipSmokeTest) {
    & (Join-Path $RepoRoot "scripts\smoke-test-portable.ps1") `
        -Executable (Join-Path $PortableRoot "dcc-mcp.exe")
    if ($LASTEXITCODE -ne 0) { throw "Portable smoke test failed" }
}

Compress-Archive -LiteralPath $PortableRoot -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Portable build ready: $ZipPath"
