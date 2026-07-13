param(
    [Parameter(Mandatory = $true)]
    [string]$Executable
)

$ErrorActionPreference = "Stop"
$Executable = (Resolve-Path -LiteralPath $Executable).Path
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SmokeRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot "build\portable-smoke"))
if (-not $SmokeRoot.StartsWith($RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Smoke output escaped the repository root: $SmokeRoot"
}
New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

function Get-FreeTcpPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

$HttpPort = Get-FreeTcpPort
do { $RegisterPort = Get-FreeTcpPort } while ($RegisterPort -eq $HttpPort)
$Stdout = Join-Path $SmokeRoot "stdout.log"
$Stderr = Join-Path $SmokeRoot "stderr.log"

$Process = Start-Process -FilePath $Executable `
    -ArgumentList @("--port", $HttpPort, "--register-port", $RegisterPort, "--log-level", "INFO") `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr

try {
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    $Snapshot = $null
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($Process.HasExited) {
            throw "Portable daemon exited early with code $($Process.ExitCode). See $Stderr"
        }
        try {
            $Snapshot = Invoke-RestMethod -Uri "http://127.0.0.1:$HttpPort/api/diagnostics" -TimeoutSec 2
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $Snapshot) { throw "Portable daemon did not become ready within 30 seconds" }
    foreach ($Tool in @("list_instances", "execute_python", "health", "screenshot")) {
        if ($Snapshot.mcp_tools -notcontains $Tool) { throw "Missing MCP tool in diagnostics: $Tool" }
    }

    $McpHeaders = @{
        Accept = "application/json, text/event-stream"
        "Content-Type" = "application/json"
    }
    $InitializeBody = @{
        jsonrpc = "2.0"
        id = 1
        method = "initialize"
        params = @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{ name = "portable-smoke"; version = "1" }
        }
    } | ConvertTo-Json -Depth 6 -Compress
    $Initialize = Invoke-WebRequest -UseBasicParsing -Method Post `
        -Uri "http://127.0.0.1:$HttpPort/mcp" -Headers $McpHeaders -Body $InitializeBody
    if ($Initialize.Content -notmatch 'protocolVersion') {
        throw "MCP initialize did not return a protocol version"
    }
    $SessionId = $Initialize.Headers["mcp-session-id"]
    if (-not $SessionId) { throw "MCP initialize did not return a session ID" }
    $McpHeaders["mcp-session-id"] = $SessionId

    $InitializedBody = @{
        jsonrpc = "2.0"
        method = "notifications/initialized"
    } | ConvertTo-Json -Compress
    Invoke-WebRequest -UseBasicParsing -Method Post `
        -Uri "http://127.0.0.1:$HttpPort/mcp" -Headers $McpHeaders -Body $InitializedBody | Out-Null

    $ToolsBody = @{
        jsonrpc = "2.0"
        id = 2
        method = "tools/list"
        params = @{}
    } | ConvertTo-Json -Compress
    $Tools = Invoke-WebRequest -UseBasicParsing -Method Post `
        -Uri "http://127.0.0.1:$HttpPort/mcp" -Headers $McpHeaders -Body $ToolsBody
    foreach ($Tool in @("list_instances", "execute_python", "health", "screenshot")) {
        if ($Tools.Content -notmatch [regex]::Escape($Tool)) {
            throw "MCP tools/list response is missing: $Tool"
        }
    }
    Write-Host "Portable smoke test passed on HTTP $HttpPort / registration $RegisterPort"
} finally {
    if (-not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        $Process.WaitForExit()
    }
}
