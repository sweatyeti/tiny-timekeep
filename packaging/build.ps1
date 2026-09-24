# Build the Windows app: one self-contained TinyTimesheet.exe in dist/.
# Run from the project root in PowerShell:  .\packaging\build.ps1
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.11 -m venv .venv
}
& .venv\Scripts\python -m pip install --upgrade pip
& .venv\Scripts\python -m pip install -r requirements-dev.txt

Write-Host "Verifying the core wiring before packaging..."
& .venv\Scripts\python main.py --check
if ($LASTEXITCODE -ne 0) { throw "main.py --check failed - not packaging a broken build." }

Write-Host "Running the core test suite..."
& .venv\Scripts\python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "core tests failed - not packaging a broken build." }

& .venv\Scripts\python -m PyInstaller packaging\timetracker.spec --noconfirm

Write-Host ""
Write-Host "Built: dist\TinyTimesheet.exe"
Write-Host "Sessions will be written to: $env:LOCALAPPDATA\TinyTimesheet\sessions"
Write-Host "Target machine needs the WebView2 runtime (present by default on Win10/11)."
