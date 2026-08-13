$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$workRoot = Join-Path $repositoryRoot "work"

foreach ($service in @("api", "web")) {
    $pidFile = Join-Path $workRoot "$service.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) {
        Write-Host "${service}: no PID file found."
        continue
    }

    $servicePid = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-Process -Id $servicePid -ErrorAction SilentlyContinue
    if ($process) {
        & taskkill.exe /PID $servicePid /T /F 2>$null | Out-Null
        Write-Host "$service process tree stopped (root PID $servicePid)."
    } else {
        Write-Host "$service was not running; removed stale PID file."
    }

    Remove-Item -LiteralPath $pidFile -Force
}
