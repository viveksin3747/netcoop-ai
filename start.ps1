$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'First run setup.ps1 to install the application dependencies.'
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html'))) {
    Push-Location frontend
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    Pop-Location
}
Write-Host 'NetCoop AI: http://127.0.0.1:8000  |  API docs: http://127.0.0.1:8000/docs'
& $pythonExe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
