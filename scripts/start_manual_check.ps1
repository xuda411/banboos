param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [string]$StagingDb = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runtimeDir = Join-Path $projectRoot "var\manual-check"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$env:BANBOOS2_LOCAL_STATE = Join-Path $runtimeDir "runtime.sqlite"
$env:BANBOOS2_EDGE_SPOOL = Join-Path $runtimeDir "edge-spool.sqlite"
if ($StagingDb) { $env:BANBOOS2_STAGING_DB = $StagingDb } else { Remove-Item Env:BANBOOS2_STAGING_DB -ErrorAction SilentlyContinue }
$env:BANBOOS2_CORS_ORIGINS = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"
Remove-Item (Join-Path $runtimeDir "api.out.log"), (Join-Path $runtimeDir "api.err.log"), `
    (Join-Path $runtimeDir "worker.out.log"), (Join-Path $runtimeDir "worker.err.log"), `
    (Join-Path $runtimeDir "web.out.log"), (Join-Path $runtimeDir "web.err.log") -Force -ErrorAction SilentlyContinue

$api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", $ApiPort `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir "api.out.log") -RedirectStandardError (Join-Path $runtimeDir "api.err.log")
$worker = Start-Process -FilePath $python -ArgumentList "-m", "apps.worker.main" `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir "worker.out.log") -RedirectStandardError (Join-Path $runtimeDir "worker.err.log")
$web = Start-Process -FilePath $python -ArgumentList "-m", "http.server", $WebPort, "--directory", (Join-Path $projectRoot "apps\web") `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtimeDir "web.out.log") -RedirectStandardError (Join-Path $runtimeDir "web.err.log")

@{ api = $api.Id; worker = $worker.Id; web = $web.Id } | ConvertTo-Json | Set-Content (Join-Path $runtimeDir "pids.json")
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/health"
        if ($health.status -eq "ok") { break }
    } catch { Start-Sleep -Milliseconds 250 }
    if ($attempt -eq 29) { throw "API did not become healthy; see $runtimeDir" }
}
Write-Host "Banboos2.0 manual check is running."
Write-Host "Web:   http://127.0.0.1:$WebPort"
Write-Host "API:   http://127.0.0.1:$ApiPort/docs"
Write-Host "Logs:  $runtimeDir"
