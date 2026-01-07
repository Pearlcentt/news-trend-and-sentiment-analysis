# Backup News Data Script
# Usage: ./backup_data.ps1

$backupDir = "backup"
if (!(Test-Path -Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputFile = "$backupDir\news_data_$timestamp.json"

Write-Host "Backing up 'historical_articles' from k8s..."
kubectl exec -n news-pipeline deployment/mongodb -- mongoexport --db news_analytics --collection historical_articles --jsonArray > $outputFile

Write-Host "Backup complete: $outputFile"
Write-Host "You can share this JSON file with others."
