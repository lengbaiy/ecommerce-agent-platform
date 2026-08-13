$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. Follow docs/STARTUP.md and create backend/.venv first."
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    throw "npm.cmd was not found. Install Node.js and reopen PowerShell."
}

Push-Location (Join-Path $repositoryRoot "backend")
try {
    & $backendPython -m ruff check app tests migrations
    & $backendPython -m ruff format --check app tests migrations
    & $backendPython -m pytest -q --cov=app --cov-fail-under=80
    & $backendPython -m coverage erase
} finally {
    Pop-Location
}

Push-Location (Join-Path $repositoryRoot "frontend")
try {
    & $npmCommand.Source run lint
    & $npmCommand.Source run format:check
    & $npmCommand.Source run build
} finally {
    Pop-Location
}

Push-Location (Join-Path $repositoryRoot "clients\mobile-ops")
try {
    & $npmCommand.Source run build
} finally {
    Pop-Location
}
