# run.ps1 - wrapper that always uses the correct 401k project venv
# Usage:
#   .\run.ps1 show-config
#   .\run.ps1 run --query-limit 5 --search-results 8 --crawl-limit 25
#   .\run.ps1 run --crawl-limit 200
#   .\run.ps1 run --skip-search --crawl-limit 5

$PYTHON = "$PSScriptRoot\.venv\Scripts\python.exe"

if (-not (Test-Path $PYTHON)) {
    Write-Error "Venv not found at $PYTHON. Run this first:"
    Write-Host "  py -3 -m venv .venv"
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

& $PYTHON main.py @args --config config/queries.yaml
