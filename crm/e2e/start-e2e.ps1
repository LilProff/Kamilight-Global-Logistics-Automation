# Starts the backend on a FRESH throwaway SQLite database plus the Vite dev server, ready for `npm test` in this folder.
#   .\start-e2e.ps1            (set E2E_DB_URL first to test against Postgres instead)
$crm = Split-Path -Parent $PSScriptRoot
$be = Join-Path $crm "backend"
$fe = Join-Path $crm "frontend"
$tmp = Join-Path ([IO.Path]::GetTempPath()) "kgl-e2e"
New-Item -ItemType Directory -Force $tmp | Out-Null
foreach ($port in 8000, 5173) {
  $p = (Get-NetTCPConnection -LocalPort $port -State Listen -EA SilentlyContinue).OwningProcess | Select-Object -Unique
  foreach ($x in $p) { Stop-Process -Id $x -Force -Confirm:$false -EA SilentlyContinue }
}
Start-Sleep 1
$stamp = Get-Date -Format "HHmmss"
$dbFile = ((Join-Path $tmp "e2e-$stamp.db") -replace "\\", "/")
$env:DATABASE_URL = if ($env:E2E_DB_URL) { $env:E2E_DB_URL } else { "sqlite:///$dbFile" }
$env:ADMIN_EMAIL = "admin@kamilightglobal.com"; $env:ADMIN_PASSWORD = "e2e-pass-123"; $env:JWT_SECRET = "e2e-secret-e2e-secret-e2e-secret-1234"
$env:RUN_WORKER = "true"; $env:SEND_RATE_PER_SECOND = "10"; $env:WA_TOKEN = ""; $env:SMTP_HOST = ""
# let automations run at any hour, checking every 5 seconds, so the test doesn't have to wait
$env:AUTOMATION_HOURS_START = "0"; $env:AUTOMATION_HOURS_END = "24"; $env:AUTOMATION_INTERVAL_SECONDS = "5"
$py = Join-Path $be ".venv\Scripts\python.exe"
Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" -WorkingDirectory $be -WindowStyle Hidden -RedirectStandardOutput "$tmp\backend.log" -RedirectStandardError "$tmp\backend.err.log"
Start-Process -FilePath "node" -ArgumentList "`"$fe\node_modules\vite\bin\vite.js`"", "`"$fe`"", "--port", "5173", "--strictPort" -WorkingDirectory $fe -WindowStyle Hidden -RedirectStandardOutput "$tmp\vite.log" -RedirectStandardError "$tmp\vite.err.log"
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep 2
  $a = curl.exe -s http://localhost:8000/health
  $b = curl.exe -s -o NUL -w "%{http_code}" http://localhost:5173/
  if ($a -and $b -eq "200") { break }
}
"backend: $a | frontend: $b | logs: $tmp"
