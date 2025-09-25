# File: Start-Backend.ps1
# Location: C:\AI files\Stratogen\backend\Start-Backend.ps1

Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# Set working directory to backend root
cd "C:\AI files\Stratogen\backend"

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start Uvicorn with clean router set
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
