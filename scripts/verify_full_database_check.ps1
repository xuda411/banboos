param(
    [string]$ApiBase = "http://127.0.0.1:8012",
    [string]$Report = ""
)

$ErrorActionPreference = "Stop"
if (-not $Report) {
    $Report = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")) "var\manual-check\full-database-test-$(Get-Date -Format yyyyMMdd-HHmmss).json"
}

function Get-Json([string]$Path) {
    return Invoke-RestMethod -UseBasicParsing -Uri ($ApiBase + $Path)
}

function Assert-Equal([object]$Actual, [object]$Expected, [string]$Message) {
    if ($Actual -ne $Expected) { throw "$Message：实际 $Actual，期望 $Expected" }
}

$health = Get-Json "/health"
$ready = Get-Json "/readyz"
$meta = Get-Json "/api/v1/meta"
$nodesResponse = Get-Json "/api/v1/nodes"
$nodes = @($nodesResponse.items)
Assert-Equal $health.status "ok" "健康检查失败"
Assert-Equal $ready.status "ready" "就绪检查失败"
Assert-Equal $meta.data_mode "staging-readonly" "Web 未使用完整 staging 数据"
if ($nodes.Count -lt 5000) { throw "节点覆盖不足：$($nodes.Count)" }

$samples = @($nodes[0], $nodes[[int]($nodes.Count / 2)], $nodes[$nodes.Count - 1]) |
    Group-Object id | ForEach-Object { $_.Group[0] }
$checks = @()
foreach ($node in $samples) {
    foreach ($market in @("日前", "实时")) {
        $summary = Get-Json "/api/v1/price/summary?node_id=$($node.id)&market=$market&start_date=2025-01-01&end_date=2026-09-30"
        $range = Get-Json "/api/v1/price/range?node_id=$($node.id)&market=$market"
        $quality = Get-Json "/api/v1/quality/summary?node_id=$($node.id)&market=$market&start_date=2025-01-01&end_date=2026-09-30"
        $aggregates = @{}
        foreach ($hours in @(2, 4)) {
            $aggregate = Get-Json "/api/v1/price/aggregates?node_id=$($node.id)&market=$market&start_date=2025-01-01&end_date=2026-09-30&duration_hours=$hours"
            if ($aggregate.valid_days -le 0 -or $aggregate.available_days -le 0) {
                throw "价差聚合无有效日期：节点 $($node.id)，市场 $market，$hours 小时"
            }
            $aggregates["${hours}h"] = [ordered]@{
                valid_days = $aggregate.valid_days
                available_days = $aggregate.available_days
                excluded_records = $aggregate.excluded_records
                multiple_source_days = $aggregate.multiple_source_days
            }
        }
        foreach ($source in @($summary.source_mode, $range.source_mode, $quality.source_mode)) {
            Assert-Equal $source "staging-readonly" "查询未使用 staging 数据"
        }
        $checks += [ordered]@{
            node_id = $node.id
            node_name = $node.name
            province = $node.province
            market = $market
            first_date = $range.first_date
            last_date = $range.last_date
            valid_days = $summary.valid_days
            data_points = $summary.data_points
            quality_records = $quality.total_records
            quality_coverage = $quality.coverage_ratio
            aggregates = $aggregates
        }
    }
}

$exports = @()
foreach ($path in @(
    "/api/v1/price/export?node_id=$($samples[0].id)&market=实时&start_date=2025-01-01&end_date=2026-09-30",
    "/api/v1/price/aggregates/export?node_id=$($samples[0].id)&market=实时&start_date=2025-01-01&end_date=2026-09-30&duration_hours=2"
)) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri ($ApiBase + $path)
    if ($response.StatusCode -ne 200 -or $response.Headers["Content-Type"] -notmatch "spreadsheetml") {
        throw "全量数据导出检查失败：$path"
    }
    $exports += [ordered]@{ path = $path; status = $response.StatusCode; bytes = $response.RawContentLength; content_type = $response.Headers["Content-Type"] }
}

$result = [ordered]@{
    report_version = "full-database-web-check-v1"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    api_base = $ApiBase
    health = $health
    ready = $ready
    meta = $meta
    node_count = $nodes.Count
    province_count = @($nodes.province | Sort-Object -Unique).Count
    sampled_nodes = @($samples | ForEach-Object { [ordered]@{ id = $_.id; name = $_.name; province = $_.province } })
    checks = $checks
    exports = $exports
    status = "passed"
}
$parent = Split-Path -Parent $Report
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Report -Encoding UTF8
$result | ConvertTo-Json -Depth 5
