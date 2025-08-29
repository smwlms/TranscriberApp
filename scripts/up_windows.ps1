Param(
  [string]$Port = "5000"
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $repoRoot

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $venvPython)) {
  Write-Host "Creating virtualenv at .venv ..."
  py -3 -m venv (Join-Path $repoRoot ".venv")
}

Write-Host "Launching backend in new PowerShell window..."
Start-Process powershell -ArgumentList @(
  '-NoExit',
  '-Command',
  "Set-Location '$repoRoot'; & '$venvPython' app.py"
)

$frontendDir = Join-Path $repoRoot "frontend"
if (Get-Command npm -ErrorAction SilentlyContinue) {
  Write-Host "Launching frontend (npm run dev) in new PowerShell window..."
  Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location '$frontendDir'; npm run dev"
  )
} else {
  Write-Warning "npm not found. Install Node.js from https://nodejs.org/en/download/"
}

