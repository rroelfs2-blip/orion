<# 
File: scripts/Save-OrionCheckpoint.ps1
Purpose: Standardized Save Project flow (checkpoint + zips + notes + index)
Usage:
  # From repo root
  # Example names: "Phase1_Batch8" or "TokenAPI_Ready"
  # Optional notes are appended to SESSION_NOTES and MANIFEST
  .\scripts\Save-OrionCheckpoint.ps1 -CheckpointName "Phase1_Batch8" -Notes "Token usage API + tests green"

Params:
  -CheckpointName: short slug (no spaces) for this checkpoint
  -Notes: short freeform notes (optional)
#>

param(
  [Parameter(Mandatory=$true)][string]$CheckpointName,
  [Parameter(Mandatory=$false)][string]$Notes = ""
)

$ErrorActionPreference = "Stop"

# ---- Config ----
$RepoRoot  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)  # -> repo root
$AppName   = "orion-backend"
$VenvPy    = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DateLocal = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$TsStamp   = Get-Date -Format "yyyyMMdd_HHmmss"  # America/Indiana/Indianapolis
$CheckDir  = Join-Path $RepoRoot "checkpoints"
$DocsDir   = Join-Path $RepoRoot "docs"
$ScriptsDir= Join-Path $RepoRoot "scripts"
$SessionNotes = Join-Path $DocsDir ("SESSION_NOTES_{0}.md" -f (Get-Date -Format "yyyy-MM-dd"))
$MasterIndex  = Join-Path $DocsDir "Master_Conversation_Index.md"

# Ensure dirs
New-Item -ItemType Directory -Force -Path $CheckDir | Out-Null
New-Item -ItemType Directory -Force -Path $DocsDir | Out-Null

# ---- Freeze state (print header) ----
"=== SAVE PROJECT ==="
"App: $AppName"
"Local Time: $DateLocal"
"Checkpoint: $CheckpointName"
if ($Notes) { "Notes: $Notes" }

# ---- Smoke checks ----
"Running smoke checks (pytest)…"
& $VenvPy -m pytest -q | Write-Host
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Pytest returned non-zero. You can Ctrl+C to abort or continue to save anyway."
}

# ---- Git checkpoint ----
Set-Location $RepoRoot
git add -A
$commitMsg = "chore(save): checkpoint $CheckpointName ($TsStamp)"
git commit -m $commitMsg | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Nothing to commit or commit failed; continuing…" -ForegroundColor Yellow
}
$tag = "checkpoint_{0}_{1}" -f $CheckpointName, $TsStamp
git tag -a $tag -m "Checkpoint $CheckpointName $TsStamp"
# Best effort push (won’t fail local save if offline)
git push | Out-Null
git push --tags | Out-Null

# ---- Build checkpoint ZIP (exclude noise) ----
$Staging = Join-Path $RepoRoot ("_staging_{0}" -f $TsStamp)
New-Item -ItemType Directory -Force -Path $Staging | Out-Null

# Mirror without heavy/private dirs
$robolog = Join-Path $RepoRoot ("robocopy_{0}.log" -f $TsStamp)
$src = $RepoRoot
$dst = $Staging
# Exclude patterns
$xd = @(".git", ".venv", "logs", "__pycache__", "node_modules")
$xf = @("*.pyc", "*.pyo", "*.log", "token.json*", "credentials.json")

$xdArgs = $xd | ForEach-Object { "/XD", $_ }
$xfArgs = $xf | ForEach-Object { "/XF", $_ }

$roboArgs = @($src, $dst, "/MIR") + $xdArgs + $xfArgs + @("/R:1","/W:1","/NFL","/NDL","/NJH","/NJS","/NP","/NS")
Start-Process -FilePath "robocopy.exe" -ArgumentList $roboArgs -Wait -NoNewWindow | Out-Null

# MANIFEST.json
$manifest = @{
  checkpoint     = $CheckpointName
  tag            = $tag
  timestamp      = $TsStamp
  repo_root      = $RepoRoot
  excludes       = $xd + $xf
  git_commit     = (git rev-parse HEAD).Trim()
  pytest_status  = $(if ($LASTEXITCODE -eq 0) { "pass" } else { "nonzero" })
  notes          = $Notes
}
$manifestPath = Join-Path $Staging "MANIFEST.json"
$manifest | ConvertTo-Json -Depth 6 | Out-File -FilePath $manifestPath -Encoding utf8

# Zip it
$ZipPath = Join-Path $CheckDir ("{0}_{1}.zip" -f $CheckpointName, $TsStamp)
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $Staging "*") -DestinationPath $ZipPath -Force

# Clean staging
Remove-Item $Staging -Recurse -Force

# ---- Session README snapshot ----
if (-not (Test-Path $SessionNotes)) {
@"
# Session Notes — $(Get-Date -Format "yyyy-MM-dd")

## What changed
- (fill me)

## Known issues / TODOs
- (fill me)

## Next-session starting steps
\`\`\`powershell
# Example
& "$($RepoRoot)\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
\`\`\`

## Version pins / env notes
- Paper-only: ON
- Port: 8010
- Secrets: not committed
"@ | Out-File -FilePath $SessionNotes -Encoding utf8
}

# Append this checkpoint info to today’s SESSION_NOTES
@"

---

### Checkpoint $CheckpointName ($TsStamp)
- Tag: \`$tag\`
- Zip: \`$ZipPath\`
- Notes: $Notes

"@ | Out-File -FilePath $SessionNotes -Encoding utf8 -Append

# ---- Master Index update ----
if (-not (Test-Path $MasterIndex)) {
@"
# Master Conversation Index (Aug 8 → Present)

"@ | Out-File -FilePath $MasterIndex -Encoding utf8
}

$resumeCue = "Resume: Start Orion → `& `"$($RepoRoot)\.venv\Scripts\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload"

@"
## $CheckpointName  —  $TsStamp
- Checkpoint tag: \`$tag\`
- ZIP: \`$ZipPath\`
- SESSION NOTES: \`$SessionNotes\`
- Resume cue: **$resumeCue**

Mini-plan for next session:
1. (fill me)
2. (fill me)
3. (fill me)

Blockers / External tasks:
- (fill me)
"@ | Out-File -FilePath $MasterIndex -Encoding utf8 -Append

# ---- Close-out ----
"`nSaved checkpoint:"
"  Tag: $tag"
"  Zip: $ZipPath"
"`nRESUME COMMAND:"
"& `"$($RepoRoot)\.venv\Scripts\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload"
