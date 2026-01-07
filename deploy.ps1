# News Trend & Sentiment Analysis - Full Pipeline Deployment Script
# Run this script in PowerShell as Administrator

param(
    [switch]$Full = $false,           # Full deployment including data processing
    [switch]$SkipMinikubeStart = $false,  # Skip minikube start if already running
    [int]$Memory = 6144,               # Memory in MB for minikube
    [int]$Cpus = 4                     # CPUs for minikube
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = Get-Location }
$K8sDir = Join-Path $ProjectRoot "k8s"

Write-Host "
=================================================================
  📰 News Trend & Sentiment Analysis - Pipeline Deployment
=================================================================
" -ForegroundColor Cyan

# Function to wait for pods
function Wait-ForPods {
    param([string]$Label, [int]$TimeoutSeconds = 120)
    Write-Host "  ⏳ Waiting for pods with label $Label..." -ForegroundColor Yellow
    kubectl wait --for=condition=ready pod -l $Label -n news-pipeline --timeout="${TimeoutSeconds}s" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ⚠️  Some pods may not be ready yet, continuing..." -ForegroundColor Yellow
    }
    else {
        Write-Host "  ✅ Pods ready!" -ForegroundColor Green
    }
}

# Step 1: Check Prerequisites
Write-Host "`n[1/8] Checking prerequisites..." -ForegroundColor White
$prereqFailed = $false

if (-not (Get-Command minikube -ErrorAction SilentlyContinue)) {
    Write-Host "  ❌ Minikube not found. Install from: https://minikube.sigs.k8s.io/docs/start/" -ForegroundColor Red
    $prereqFailed = $true
}
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "  ❌ kubectl not found. Run: winget install Kubernetes.kubectl" -ForegroundColor Red
    $prereqFailed = $true
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "  ❌ Docker not found. Install Docker Desktop first." -ForegroundColor Red
    $prereqFailed = $true
}

if ($prereqFailed) {
    Write-Host "`n❌ Prerequisites missing. Install them and rerun this script." -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ All prerequisites found!" -ForegroundColor Green

# Step 2: Start Minikube
if (-not $SkipMinikubeStart) {
    Write-Host "`n[2/8] Starting Minikube cluster..." -ForegroundColor White
    $status = minikube status --format='{{.Host}}' 2>$null
    if ($status -eq "Running") {
        Write-Host "  ✅ Minikube already running!" -ForegroundColor Green
    }
    else {
        Write-Host "  Starting minikube with ${Memory}MB RAM and ${Cpus} CPUs..." -ForegroundColor Yellow
        minikube start --memory=$Memory --cpus=$Cpus --driver=docker
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ❌ Failed to start Minikube" -ForegroundColor Red
            exit 1
        }
        Write-Host "  ✅ Minikube started!" -ForegroundColor Green
    }
}
else {
    Write-Host "`n[2/8] Skipping Minikube start (--SkipMinikubeStart)" -ForegroundColor Yellow
}

# Step 3: Deploy Foundation
Write-Host "`n[3/8] Deploying foundation (namespace & storage)..." -ForegroundColor White
kubectl apply -f "$K8sDir/00-namespace.yaml"
kubectl apply -f "$K8sDir/11-persistent-volumes.yaml"
Write-Host "  ✅ Foundation deployed!" -ForegroundColor Green

# Step 4: Deploy Core Infrastructure
Write-Host "`n[4/8] Deploying core infrastructure (Kafka & MongoDB)..." -ForegroundColor White
kubectl apply -f "$K8sDir/01-kafka.yaml"
Write-Host "  ⏳ Waiting 45s for Kafka to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 45
kubectl apply -f "$K8sDir/02-mongodb.yaml"
Start-Sleep -Seconds 15
Wait-ForPods "app=mongodb"
Write-Host "  ✅ Core infrastructure deployed!" -ForegroundColor Green

# Step 5: Deploy Processing Layer
Write-Host "`n[5/8] Deploying processing layer (Spark & HDFS)..." -ForegroundColor White
kubectl apply -f "$K8sDir/03-spark.yaml"
kubectl apply -f "$K8sDir/07-hdfs.yaml"
Wait-ForPods "app=spark-master"
Write-Host "  ✅ Processing layer deployed!" -ForegroundColor Green

# Step 6: Deploy Serving Layer
Write-Host "`n[6/8] Deploying serving layer (Trino, Grafana, Cassandra)..." -ForegroundColor White
kubectl apply -f "$K8sDir/04-trino.yaml"
kubectl apply -f "$K8sDir/05-grafana.yaml"
kubectl apply -f "$K8sDir/08-cassandra.yaml"
kubectl apply -f "$K8sDir/10-airflow.yaml"
Write-Host "  ✅ Serving layer deployed!" -ForegroundColor Green

# Step 7: Deploy Applications
Write-Host "`n[7/8] Deploying applications (Crawler, Dashboard, Alerts)..." -ForegroundColor White
kubectl apply -f "$K8sDir/06-crawler.yaml"
kubectl apply -f "$K8sDir/09-streamlit.yaml"
kubectl apply -f "$K8sDir/19-alerts-deployment.yaml"
Wait-ForPods "app=streamlit-dashboard"
Write-Host "  ✅ Applications deployed!" -ForegroundColor Green

# Step 8: Deploy Processing Jobs
Write-Host "`n[8/8] Deploying processing jobs..." -ForegroundColor White
kubectl apply -f "$K8sDir/12-spark-streaming-job.yaml"
kubectl apply -f "$K8sDir/13-spark-batch-cronjob.yaml"
Write-Host "  ✅ Processing jobs deployed!" -ForegroundColor Green

# Full deployment: Run data ingestion and processing
if ($Full) {
    Write-Host "`n[FULL] Running data ingestion..." -ForegroundColor Cyan
    kubectl apply -f "$K8sDir/14-fresh-crawler-job.yaml"
    Write-Host "  ⏳ Waiting for crawler job to complete..." -ForegroundColor Yellow
    kubectl wait --for=condition=complete job/fresh-news-crawler -n news-pipeline --timeout=300s 2>$null
    
    Write-Host "`n[FULL] Running sentiment analysis..." -ForegroundColor Cyan
    kubectl apply -f "$K8sDir/15-process-historical-job.yaml"
    kubectl wait --for=condition=complete job/process-historical-data -n news-pipeline --timeout=600s 2>$null
    
    Write-Host "`n[FULL] Running category classification..." -ForegroundColor Cyan
    kubectl apply -f "$K8sDir/16-classify-articles-job.yaml"
    kubectl wait --for=condition=complete job/classify-articles -n news-pipeline --timeout=600s 2>$null
    
    Write-Host "`n[FULL] Running data quality validation..." -ForegroundColor Cyan
    kubectl apply -f "$K8sDir/18-data-quality-job.yaml"
    kubectl wait --for=condition=complete job/data-quality-check -n news-pipeline --timeout=300s 2>$null
    
    Write-Host "  ✅ Data processing complete!" -ForegroundColor Green
}

# Summary
Write-Host "
=================================================================
  ✅ DEPLOYMENT COMPLETE!
=================================================================

📊 Pod Status:
" -ForegroundColor Green

kubectl get pods -n news-pipeline --no-headers | ForEach-Object {
    $parts = $_ -split '\s+'
    $status = $parts[2]
    $icon = if ($status -eq "Running" -or $status -eq "Completed") { "✅" } else { "⏳" }
    Write-Host "  $icon $($parts[0]) - $status"
}

Write-Host "
🌐 Access Dashboard:
  kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
  Then open: http://localhost:8501

📈 Other Services:
  Grafana:  kubectl port-forward -n news-pipeline svc/grafana 3000:3000
  Trino:    kubectl port-forward -n news-pipeline svc/trino 8080:8080
  MongoDB:  kubectl port-forward -n news-pipeline svc/mongodb 27017:27017

📋 Useful Commands:
  kubectl get pods -n news-pipeline          # View all pods
  kubectl logs -f deployment/XX -n news-pipeline   # View logs
  minikube dashboard                          # Open K8s dashboard

" -ForegroundColor Cyan
