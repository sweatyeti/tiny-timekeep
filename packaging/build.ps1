# Build the Windows app: one self-contained tinyTimekeep.exe in dist/.
# Run from the project root in PowerShell:  .\packaging\build.ps1
param(
    [switch]$RecreateVenv  # delete an existing .venv and build a fresh one
)

$ErrorActionPreference = "Stop"

$RequiredPythonVersion = "3.14.7"
$venvPython = ".venv\Scripts\python.exe"

function Get-VenvPythonVersion {
    param([string]$PythonPath)
    $raw = (& $PythonPath -V 2>&1 | Out-String).Trim()
    return ($raw -replace '^Python\s+', '').Trim()
}

if ((Test-Path ".venv") -and $RecreateVenv) {
    Remove-Item -Path ".venv" -Recurse -Force
}

if (Test-Path ".venv") {
    $detectedVersion = Get-VenvPythonVersion -PythonPath $venvPython
    if ($detectedVersion -eq $RequiredPythonVersion) {
        Write-Host "Reusing existing .venv with Python $detectedVersion."
    } else {
        throw "Existing .venv was built with Python $detectedVersion but this build requires Python $RequiredPythonVersion. Re-run with -RecreateVenv to delete and rebuild it, or delete the .venv folder manually."
    }
} else {
    Write-Host "Creating virtual environment with Python 3.14..."
    py -3.14 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "could not create .venv with Python 3.14 - is it installed?" }
    $detectedVersion = Get-VenvPythonVersion -PythonPath $venvPython
    if ($detectedVersion -ne $RequiredPythonVersion) {
        throw "New .venv was created with Python $detectedVersion but this build requires Python $RequiredPythonVersion. Ensure Python $RequiredPythonVersion is installed and re-run."
    }
}

& .venv\Scripts\python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed - not packaging a broken build." }
& .venv\Scripts\python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "dependency install failed - not packaging a broken build." }

Write-Host "Verifying the core wiring before packaging..."
& .venv\Scripts\python main.py --check
if ($LASTEXITCODE -ne 0) { throw "main.py --check failed - not packaging a broken build." }

Write-Host "Running the app-specific test suite..."
& .venv\Scripts\python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "app tests failed - not packaging a broken build." }

& .venv\Scripts\python -m PyInstaller packaging\keeper-of-time.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed - not packaging a broken build." }
if (-not (Test-Path "dist\tinyTimekeep.exe")) { throw "dist\tinyTimekeep.exe was not produced." }

Write-Host ""
Write-Host "Built: dist\tinyTimekeep.exe"
Write-Host "New-install sessions default: $env:LOCALAPPDATA\tinyTimekeep\sessions"
Write-Host "An existing KeeperOfTime\sessions folder remains in use; files are not moved automatically."
Write-Host "Target machine needs the WebView2 runtime (present by default on Win10/11)."