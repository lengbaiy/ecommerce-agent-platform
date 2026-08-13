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
    & $backendPython -m ruff check app tests
    & $backendPython -m ruff format --check app tests
    & $backendPython -m pytest -q
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
