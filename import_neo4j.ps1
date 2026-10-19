param(
    [Parameter(Mandatory=$true)][string]$Neo4jHome,
    [string]$PreparedDir = (Join-Path $PSScriptRoot 'neo4j_import')
)
$ErrorActionPreference = 'Stop'
$admin = Join-Path $Neo4jHome 'bin\neo4j-admin.bat'
$importDir = Join-Path $Neo4jHome 'import'
if (-not (Test-Path -LiteralPath $admin)) { throw "neo4j-admin not found: $admin" }
if (-not (Test-Path -LiteralPath $PreparedDir)) { throw "Prepared CSV folder not found: $PreparedDir" }
New-Item -ItemType Directory -Force -Path $importDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'results') | Out-Null
$files = @('customers_import.csv','accounts_import.csv','devices_import.csv','owns.csv','used_device.csv','transfers_import.csv')
foreach ($name in $files) { Copy-Item -LiteralPath (Join-Path $PreparedDir $name) -Destination (Join-Path $importDir $name) -Force }
Push-Location (Split-Path -Parent $admin)
try {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    & $admin database import full neo4j --id-type=integer `
        --nodes=Customer=customers_import.csv `
        --nodes=Account=accounts_import.csv `
        --nodes=Device=devices_import.csv `
        --relationships=OWNS=owns.csv `
        --relationships=USED_DEVICE=used_device.csv `
        --relationships=TRANSFER=transfers_import.csv
    if ($LASTEXITCODE -ne 0) { throw "neo4j-admin import failed with exit code $LASTEXITCODE" }
    $timer.Stop()
    "import_seconds=$([math]::Round($timer.Elapsed.TotalSeconds,3))" | Tee-Object -FilePath (Join-Path $PSScriptRoot 'results\neo4j_import_time.txt')
} finally { Pop-Location }
