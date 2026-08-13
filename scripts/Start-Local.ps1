param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $repositoryRoot "backend"
$frontendRoot = Join-Path $repositoryRoot "frontend"
$workRoot = Join-Path $repositoryRoot "work"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$backendLog = Join-Path $workRoot "api.log"
$backendErrorLog = Join-Path $workRoot "api.error.log"
$frontendLog = Join-Path $workRoot "web.log"
$frontendErrorLog = Join-Path $workRoot "web.error.log"

function Assert-PortAvailable {
    param([int]$Port, [string]$ServiceName)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "$ServiceName cannot start: port $Port is already in use (PID $($listener[0].OwningProcess))."
    }
}

function Wait-Endpoint {
    param([string]$Url, [string]$ServiceName, [string]$ErrorLog)

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    $details = if (Test-Path $ErrorLog) { Get-Content -LiteralPath $ErrorLog -Tail 20 | Out-String } else { "No error log was created." }
    throw "$ServiceName did not become ready.`n$details"
}

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. Follow docs/STARTUP.md and create backend/.venv first."
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    throw "npm.cmd was not found. Install Node.js and reopen PowerShell."
}

if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    throw "Frontend dependencies are missing. Run 'npm install' in the frontend directory first."
}

Assert-PortAvailable -Port $ApiPort -ServiceName "API"
Assert-PortAvailable -Port $WebPort -ServiceName "Web"
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null

$backendProcess = Start-Process -FilePath $backendPython -WorkingDirectory $backendRoot `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "$ApiPort" `
    -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrorLog -WindowStyle Hidden -PassThru

$previousProxyTarget = $env:VITE_API_PROXY_TARGET
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
try {
    $frontendProcess = Start-Process -FilePath $npmCommand.Source -WorkingDirectory $frontendRoot `
        -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "$WebPort" `
        -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog -WindowStyle Hidden -PassThru
} finally {
    $env:VITE_API_PROXY_TARGET = $previousProxyTarget
}

$backendProcess.Id | Set-Content -LiteralPath (Join-Path $workRoot "api.pid")
$frontendProcess.Id | Set-Content -LiteralPath (Join-Path $workRoot "web.pid")

try {
    Wait-Endpoint -Url "http://127.0.0.1:$ApiPort/ready" -ServiceName "API" -ErrorLog $backendErrorLog
    Wait-Endpoint -Url "http://127.0.0.1:$WebPort/" -ServiceName "Web" -ErrorLog $frontendErrorLog
} catch {
    foreach ($processId in @($backendProcess.Id, $frontendProcess.Id)) {
        & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
    }
    throw
}

Write-Host "Project started successfully."
Write-Host "Web:      http://127.0.0.1:$WebPort/"
Write-Host "API docs: http://127.0.0.1:$ApiPort/docs"
Write-Host "Health:   http://127.0.0.1:$ApiPort/health"
Write-Host "Ready:    http://127.0.0.1:$ApiPort/ready"
Write-Host "Logs:     $workRoot"
