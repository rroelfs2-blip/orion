Param(
  [int]$Port = 8010,
  [string]$BindHost = "127.0.0.1",
  # Use your installed Python via 'py' launcher; 3.13 is OK on your box
  [string]$PythonTag = "3.13"
)

$RootDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir  = Join-Path $RootDir ".venv"
$VenvPy   = Join-Path $VenvDir "Scripts\python.exe"
$AppDir   = Join-Path $RootDir "app"
$Logs     = Join-Path $RootDir "logs"
$Config   = Join-Path $RootDir "config"
$ReqTxt   = Join-Path $RootDir "requirements.txt"

# Ensure dirs
New-Item -ItemType Directory -Force -Path $Logs   | Out-Null
New-Item -ItemType Directory -Force -Path $Config | Out-Null

# Create venv if missing
if (-not (Test-Path $VenvPy)) {
  Write-Host "Creating venv at $VenvDir using Python $PythonTag"
  py -$PythonTag -m venv $VenvDir
  if (-not (Test-Path $VenvPy)) {
    Write-Warning "Failed with Python $PythonTag, trying 3.11 fallback..."
    py -3.11 -m venv $VenvDir
  }
  if (-not (Test-Path $VenvPy)) {
    throw "Unable to create virtual environment (.venv). Check your Python launcher ('py -0p')."
  }

  & $VenvPy -m pip install --upgrade pip
  if (Test-Path $ReqTxt) {
    & $VenvPy -m pip install -r $ReqTxt
  } else {
    # Minimal deps if requirements.txt is missing
    & $VenvPy -m pip install fastapi uvicorn[standard] pydantic python-dotenv httpx pytest
  }
}

Write-Host ("Python  : {0}" -f $VenvPy)
Write-Host ("CWD     : {0}" -f $RootDir)
Write-Host ("Host    : {0}" -f $BindHost)
Write-Host ("Port    : {0}" -f $Port)
Write-Host ("AppDir  : {0}" -f $AppDir)
Write-Host ("Routers : app.routers.risk, app.routers.orders, app.routers.system, app.routers.logs, app.routers.pnl, app.routers.alpaca")

Push-Location $RootDir
try {
  & $VenvPy -m uvicorn app.main:app --host $BindHost --port $Port --reload
} finally {
  Pop-Location
}
