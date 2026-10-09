param(
    [int]$ApiPort = 8012,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$stagingDb = Join-Path $projectRoot "var\migrations\legacy-full-20260923.sqlite3"
$legacyDb = Join-Path $projectRoot "var\data-quality\legacy-price-clean-20261003.sqlite3"
$financialTemplate = Join-Path $projectRoot "var\templates\独立储能项目经济性测算工具.xlsm"

foreach ($path in @($stagingDb, $legacyDb, $financialTemplate)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "全量 Web 测试依赖文件不存在：$path"
    }
}

& (Join-Path $PSScriptRoot "start_manual_check.ps1") `
    -ApiPort $ApiPort `
    -WebPort $WebPort `
    -StagingDb $stagingDb `
    -LegacyDb $legacyDb `
    -FinancialTemplate $financialTemplate `
    -NoPositiveFixture

if (-not $?) {
    throw "全量 Web 测试服务启动失败。"
}
