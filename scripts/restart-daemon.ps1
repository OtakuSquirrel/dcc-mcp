# Called by start-daemon.bat before launching the new daemon.
$ErrorActionPreference = "Stop"

function Test-DccDaemonCommandLine {
    param([string]$CommandLine, [string]$PythonPath, [string]$EntryPoint)

    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    $python = '"?' + [regex]::Escape($PythonPath) + '"?'
    $entry = '"?' + [regex]::Escape($EntryPoint) + '"?'
    # Match executable arguments, not a path merely mentioned in another command.
    return ($CommandLine -match ('^' + $python + '\s+-m\s+dcc_mcp(?:\s|$)')) -or
        ($CommandLine -match ('^(?:' + $python + '\s+)?' + $entry + '(?:\s|$)'))
}

# Dot-sourcing exposes the matcher for tests without stopping any process.
if ($MyInvocation.InvocationName -eq '.') { return }

try {
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
    $pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
    $entryPoint = Join-Path $repoRoot '.venv\Scripts\dcc-mcp.exe'
    Set-Location -LiteralPath $repoRoot

    $bindJson = & $pythonPath -c 'import json; from dcc_mcp import config; print(json.dumps(dict(http=config.http_bind(), register=config.register_bind())))'
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the daemon configuration.' }
    $binds = $bindJson | ConvertFrom-Json
    $ports = @([int]$binds.http[1], [int]$binds.register[1])

    $processes = @(Get-CimInstance Win32_Process)
    $oldDaemons = @($processes | Where-Object {
        $_.ProcessId -ne $PID -and
        ((Test-DccDaemonCommandLine -CommandLine $_.CommandLine -PythonPath $pythonPath -EntryPoint $entryPoint) -or
         ($_.ExecutablePath -eq $pythonPath -and $_.CommandLine -match '^"?(?:\.\\)?\.venv\\Scripts\\python.exe"?\s+-m\s+dcc_mcp(?:\s|$)'))
    })
    $oldIds = @($oldDaemons | ForEach-Object { $_.ProcessId })
    # Windows venv Python can redirect to a child using the base interpreter.
    # Accept that child only when its parent is verified and the command matches.
    foreach ($child in $processes) {
        if ($child.ParentProcessId -in $oldIds -and $child.ProcessId -notin $oldIds) {
            $parent = $oldDaemons | Where-Object { $_.ProcessId -eq $child.ParentProcessId } | Select-Object -First 1
            if ($child.CommandLine -eq $parent.CommandLine) { $oldDaemons += $child }
        }
    }
    $oldIds = @($oldDaemons | ForEach-Object { $_.ProcessId })
    $listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $ports })
    $foreignListeners = @($listeners | Where-Object { $_.OwningProcess -notin $oldIds })
    if ($foreignListeners.Count -gt 0) {
        $details = ($foreignListeners | ForEach-Object { "port $($_.LocalPort) (PID $($_.OwningProcess))" } | Sort-Object -Unique) -join ', '
        throw "Another application is using $details. It was not stopped."
    }

    foreach ($oldDaemon in $oldDaemons) {
        $running = Get-Process -Id $oldDaemon.ProcessId -ErrorAction SilentlyContinue
        if ($null -ne $running) {
            Write-Host "Stopping previous dcc-mcp (PID $($oldDaemon.ProcessId))..."
            try { Stop-Process -InputObject $running -Force }
            catch { if (Get-Process -Id $oldDaemon.ProcessId -ErrorAction SilentlyContinue) { throw } }
        }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $ports })
        if ($listeners.Count -eq 0) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Daemon ports did not become available within 10 seconds.' }
        Start-Sleep -Milliseconds 200
    } while ($true)

    Write-Host "  MCP:       http://$($binds.http[0]):$($binds.http[1])/mcp"
    Write-Host "  Dashboard: http://$($binds.http[0]):$($binds.http[1])/"
    Write-Host "  Register:  $($binds.register[0]):$($binds.register[1])"
    exit 0
} catch {
    Write-Host "Restart failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
