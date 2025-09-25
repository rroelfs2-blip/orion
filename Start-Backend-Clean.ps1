# WorkingDir: C:\AI files\Stratogen\backend
# Window: Server window (PowerShell)

$ProjectRoot = "C:\AI files\Stratogen"
$Port = "8001"
$ServerHost = "127.0.0.1"

$env:PYTHONPATH = "$ProjectRoot\\backend\\app"
$env:DOTENV_CONFIG_PATH = "$ProjectRoot\\backend\\.env"
$env:GOOGLE_SECRETS_DIR = "$ProjectRoot\\secrets\\google"
$env:QUANTA_SECRET_DIR = "$ProjectRoot\\secrets\\quanta"

$venv = Join-Path -Path "$ProjectRoot\\backend\\.venv\\Scripts" -ChildPath "Activate.ps1"

if (Test-Path $venv) {
    Write-Host "Activating venv at: $venv"
    & $venv
} else {
    Write-Warning "Virtual environment not found at $venv"
}

cd "$ProjectRoot\\backend"

python -m uvicorn app.main:app `
  --app-dir "backend/app" `
  --host $ServerHost `
  --port $Port `
  --log-level info
