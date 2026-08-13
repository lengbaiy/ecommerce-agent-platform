$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$outputPath = Join-Path $repositoryRoot "docs\openapi.json"
$backendPython = Join-Path $repositoryRoot "backend\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment is missing. Create backend/.venv first."
}

Push-Location (Join-Path $repositoryRoot "backend")
try {
    & $backendPython -c "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))" |
        Set-Content -Encoding utf8 $outputPath
} finally {
    Pop-Location
}

Write-Host "OpenAPI 文档已导出：$outputPath"
