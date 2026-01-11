# Restore News Data Script
# Usage: ./restore_data.ps1 [-Timestamp "20260110_153557"]

param(
    [string]$Timestamp = "20260110_153557"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot | Split-Path -Parent
$backupDir = Join-Path $ProjectRoot "backup"

$histFile = Join-Path $backupDir "historical_articles_$Timestamp.json"
$rtFile = Join-Path $backupDir "processed_news_$Timestamp.json"
$trendsFile = Join-Path $backupDir "rt_trends_$Timestamp.json"

if (-not (Test-Path $histFile)) {
    Write-Error "Backup file not found: $histFile"
    exit 1
}

Write-Host "Restoring data from timestamp: $Timestamp" -ForegroundColor Cyan
Write-Host "Backup directory: $backupDir" -ForegroundColor Gray

# Get MongoDB Pod
$pod = kubectl get pods -n news-pipeline -l app=mongodb -o jsonpath="{.items[0].metadata.name}"
if (-not $pod) {
    Write-Error "MongoDB pod not found. Is the cluster running?"
    exit 1
}
Write-Host "Target Pod: $pod" -ForegroundColor Gray

# Helper: Convert file to UTF-8 (no BOM) and copy to pod
function Import-ToPod {
    param($LocalFile, $RemotePath, $Db, $Collection)
    
    Write-Host "  Reading file..." -ForegroundColor DarkGray
    $content = Get-Content -Path $LocalFile -Raw -Encoding UTF8
    
    # Write to a temp file in the project root (avoids path issues)
    $tempFile = Join-Path $ProjectRoot "temp_import.json"
    [System.IO.File]::WriteAllText($tempFile, $content, [System.Text.UTF8Encoding]::new($false))
    
    Write-Host "  Copying to pod..." -ForegroundColor DarkGray
    # Build the destination string properly
    $destination = "news-pipeline/" + $pod + ":" + $RemotePath
    
    # Use full path for kubectl
    kubectl cp "$tempFile" "$destination"
    $copyResult = $LASTEXITCODE
    
    # Cleanup temp file
    Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
    
    if ($copyResult -ne 0) {
        Write-Error "Failed to copy file to pod (exit code: $copyResult)"
        exit 1
    }
    
    Write-Host "  Importing into MongoDB ($Db.$Collection)..." -ForegroundColor DarkGray
    kubectl exec -n news-pipeline $pod -- mongoimport --db $Db --collection $Collection --file $RemotePath --jsonArray --drop
    
    # Cleanup in pod
    kubectl exec -n news-pipeline $pod -- rm $RemotePath 2>$null
}

# 1. Restore Historical Data
Write-Host "`nRestoring 'historical_articles' (Batch Layer)..." -ForegroundColor Yellow
Import-ToPod -LocalFile $histFile -RemotePath "/tmp/hist.json" -Db "news_analytics" -Collection "historical_articles"

# 2. Restore RT Data
Write-Host "`nRestoring 'processed_news' (Speed Layer)..." -ForegroundColor Yellow
Import-ToPod -LocalFile $rtFile -RemotePath "/tmp/rt.json" -Db "news_rt" -Collection "processed_news"

# 3. Restore Trends
Write-Host "`nRestoring 'rt_trends'..." -ForegroundColor Yellow
Import-ToPod -LocalFile $trendsFile -RemotePath "/tmp/trends.json" -Db "news_rt" -Collection "rt_trends"

Write-Host "`nRestore Complete! 🎉" -ForegroundColor Green
Write-Host "Refresh the dashboard to see your data." -ForegroundColor Cyan
