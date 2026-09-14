$ErrorActionPreference = "SilentlyContinue"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$runtimeDir = Join-Path $projectRoot "var\manual-check"
$pidFile = Join-Path $runtimeDir "pids.json"
if (Test-Path $pidFile) {
    $pids = Get-Content $pidFile | ConvertFrom-Json
    foreach ($id in @($pids.api, $pids.worker, $pids.web)) {
        if ($id) { Stop-Process -Id ([int]$id) -Force }
    }
    Remove-Item $pidFile -Force
}
Write-Host "Banboos2.0 manual check processes stopped."
