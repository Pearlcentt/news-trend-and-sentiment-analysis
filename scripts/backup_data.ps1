# Backup News Data Script
# Usage: ./backup_data.ps1

$backupDir = "backup"
if (!(Test-Path -Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
Write-Host "Backing up 'historical_articles'..."
kubectl exec -n news-pipeline deployment/mongodb -- mongoexport --db news_analytics --collection historical_articles --jsonArray > "$backupDir\historical_articles_$timestamp.json"

Write-Host "Backing up 'processed_news' (RT)..."
kubectl exec -n news-pipeline deployment/mongodb -- mongoexport --db news_rt --collection processed_news --jsonArray > "$backupDir\processed_news_$timestamp.json"

Write-Host "Backing up 'rt_trends'..."
kubectl exec -n news-pipeline deployment/mongodb -- mongoexport --db news_rt --collection rt_trends --jsonArray > "$backupDir\rt_trends_$timestamp.json"

Write-Host "Backup complete. Files saved to $backupDir"
