# Orion Backend (standardized package)

## Quick start (Windows, PowerShell)
```powershell
# 1) Create venv and install deps
cd .\backend
py -3.11 -m venv .venv
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt

# 2) Copy .env.example to .env and adjust as needed
Copy-Item .env.example .env

# 3) Run
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```
## Endpoints to verify
- `/healthz`
- `/openapi.json`
- `/api/risk/state`, `/api/risk/update`, `/api/risk/evaluate`, `/api/risk/cooloff/{active}`, `/api/risk/circuit/clear`
- `/api/orders/preview`

## Notes
- Paper-only by default; no live orders unless explicitly enabled.
- Logs under `./logs`; config under `./config` (created on start).
- See `.env.example` for tunables.
