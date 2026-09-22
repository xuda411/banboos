param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [string]$StagingDb = "",
    [string]$LegacyDb = "",
    [string]$FinancialTemplate = "",
    [switch]$NoPositiveFixture
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runtimeDir = Join-Path $projectRoot "var\manual-check"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$pidFile = Join-Path $runtimeDir "pids.json"
if (Test-Path $pidFile) {
    try {
        $previous = Get-Content -Raw $pidFile | ConvertFrom-Json
        foreach ($name in @("api", "worker", "web")) {
            $previousPid = [int]$previous.$name
            if ($previousPid -gt 0 -and (Get-Process -Id $previousPid -ErrorAction SilentlyContinue)) {
                Stop-Process -Id $previousPid -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 300
    } catch {
        Write-Warning "无法读取上一轮服务 PID 文件，将继续执行端口检查：$($_.Exception.Message)"
    }
}

function Assert-PortFree([int]$Port, [string]$Name) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $owners = ($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        throw "$Name 端口 $Port 已被进程 $owners 占用。请停止该服务后再启动，避免重复 API/Worker。"
    }
}

Assert-PortFree $ApiPort "API"
Assert-PortFree $WebPort "Web"

$env:BANBOOS2_LOCAL_STATE = Join-Path $runtimeDir "runtime.sqlite"
$env:BANBOOS2_EDGE_SPOOL = Join-Path $runtimeDir "edge-spool.sqlite"
if ($StagingDb) { $env:BANBOOS2_STAGING_DB = $StagingDb } else { Remove-Item Env:BANBOOS2_STAGING_DB -ErrorAction SilentlyContinue }
if ($LegacyDb) { $env:BANBOOS2_LEGACY_DB = $LegacyDb } else { Remove-Item Env:BANBOOS2_LEGACY_DB -ErrorAction SilentlyContinue }
if ($FinancialTemplate) { $env:BANBOOS2_FINANCIAL_TEMPLATE = $FinancialTemplate } else { Remove-Item Env:BANBOOS2_FINANCIAL_TEMPLATE -ErrorAction SilentlyContinue }
$positiveFixture = Join-Path $runtimeDir "positive-staging.sqlite3"
if (-not $StagingDb -and -not $NoPositiveFixture) {
    if (-not (Test-Path $positiveFixture)) {
        & $python (Join-Path $projectRoot "scripts\create_manual_fixture.py") --target $positiveFixture
        if ($LASTEXITCODE -ne 0) { throw "正向人工测试数据夹具生成失败。" }
    }
    $env:BANBOOS2_STAGING_DB = $positiveFixture
}
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
Write-Host "Web:   http://127.0.0.1:$WebPort/?apiPort=$ApiPort"
Write-Host "API:   http://127.0.0.1:$ApiPort/docs"
Write-Host "Logs:  $runtimeDir"
