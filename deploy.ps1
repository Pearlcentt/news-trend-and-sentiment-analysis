# News Trend and Sentiment Analysis - Full Pipeline Deployment Script
# Run this script in PowerShell as Administrator

param(
    [switch]$Full = $false,           # Full deployment including data processing
    [switch]$SkipMinikubeStart = $false,  # Skip minikube start if already running
    [int]$Memory = 8192,               # Memory in MB for minikube (8GB for Airflow + Spark)
    [int]$Cpus = 4                     # CPUs for minikube
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = Get-Location }
$K8sDir = Join-Path $ProjectRoot "k8s"

Write-Host @"

=================================================================
  News Trend and Sentiment Analysis - Pipeline Deployment
=================================================================

"@ -ForegroundColor Cyan

# Function to wait for pods
function Wait-ForPods {
    param([string]$Label, [int]$TimeoutSeconds = 120)
    Write-Host "  Waiting for pods with label $Label..." -ForegroundColor Yellow
    kubectl wait --for=condition=ready pod -l $Label -n news-pipeline --timeout="${TimeoutSeconds}s" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Some pods may not be ready yet, continuing..." -ForegroundColor Yellow
    }
    else {
        Write-Host "  Pods ready!" -ForegroundColor Green
    }
}

# Step 1: Check Prerequisites
Write-Host "`n[1/7] Checking prerequisites..." -ForegroundColor White
$prereqFailed = $false

if (-not (Get-Command minikube -ErrorAction SilentlyContinue)) {
    Write-Host "  Minikube not found. Install from: https://minikube.sigs.k8s.io/docs/start/" -ForegroundColor Red
    $prereqFailed = $true
}
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "  kubectl not found. Run: winget install Kubernetes.kubectl" -ForegroundColor Red
    $prereqFailed = $true
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "  Docker not found. Install Docker Desktop first." -ForegroundColor Red
    $prereqFailed = $true
}

if ($prereqFailed) {
    Write-Host "`nPrerequisites missing. Install them and rerun this script." -ForegroundColor Red
    exit 1
}
Write-Host "  All prerequisites found!" -ForegroundColor Green

# Step 2: Start Minikube
if (-not $SkipMinikubeStart) {
    Write-Host "`n[2/7] Starting Minikube cluster..." -ForegroundColor White
    $status = $null
    try {
        $status = minikube status --format='{{.Host}}' 2>&1 | Out-String
    }
    catch {
        $status = ""
    }
    
    if ($status -match "Running") {
        Write-Host "  Minikube already running!" -ForegroundColor Green
    }
    else {
        Write-Host "  Starting minikube with ${Memory}MB RAM and ${Cpus} CPUs..." -ForegroundColor Yellow
        minikube start --memory=$Memory --cpus=$Cpus --driver=docker
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  Failed to start Minikube" -ForegroundColor Red
            exit 1
        }
        Write-Host "  Minikube started!" -ForegroundColor Green
    }
}
else {
    Write-Host "`n[2/7] Skipping Minikube start (--SkipMinikubeStart)" -ForegroundColor Yellow
}

# Step 2.5: Build Docker Images (Required for Fresh Install)
Write-Host "`n[2.5/7] Building Docker images (Crawler & Dashboard)..." -ForegroundColor White
Write-Host "  Building news-crawler:latest..." -ForegroundColor Gray
# Build from project root with explicit Dockerfile path (Dockerfile expects project root context)
minikube image build -t news-crawler:latest -f ./crawler/Dockerfile .
Write-Host "  Building news-dashboard:latest..." -ForegroundColor Gray
# Dashboard uses simple context (all files in ./dashboard)
minikube image build -t news-dashboard:latest ./dashboard
Write-Host "  Images built!" -ForegroundColor Green

# Step 3: Deploy Foundation
Write-Host "`n[3/7] Deploying foundation (namespace and storage)..." -ForegroundColor White
kubectl apply -f "$K8sDir/00-namespace.yaml"
kubectl apply -f "$K8sDir/10-persistent-volumes.yaml"
Write-Host "  Foundation deployed!" -ForegroundColor Green

# Step 3.5: Create ConfigMaps (Code Sync)
Write-Host "`n[3.5/7] Creating ConfigMaps..." -ForegroundColor White

# Helper to recreate configmap
function Recreate-ConfigMap {
    param($Name, $Files)
    kubectl delete configmap $Name -n news-pipeline --ignore-not-found 2>$null
    
    $args = @("create", "configmap", $Name, "-n", "news-pipeline")
    foreach ($file in $Files) {
        if (Test-Path $file) {
            $args += "--from-file=$file"
        }
        else {
            Write-Host "  Warning: File not found: $file" -ForegroundColor Yellow
        }
    }
    
    # Execute kubectl with arguments
    kubectl @args
}

# 1. spark-jobs-code
Recreate-ConfigMap "spark-jobs-code" @(
    "jobs/batch/batch_pipeline.py",
    "jobs/streaming/streaming_pipeline.py",
    "jobs/streaming/alert_consumer.py",
    "jobs/quality/checkpoint_runner.py",
    "jobs/analytics/ml_pipeline.py",
    "jobs/analytics/time_series.py",
    "jobs/analytics/graph_analytics.py",
    "jobs/analytics/advanced_aggregations.py",
    "jobs/utils/sentiment.py",
    "jobs/utils/spark_utils.py",
    "jobs/config/rt-config.yaml",
    "jobs/config/batch-config.yaml",
    "jobs/config/analytics-config.yaml"
)

# 2. crawler-code
Recreate-ConfigMap "crawler-code" @(
    "crawler/news_crawler.py",
    "crawler/historical_crawler.py",
    "crawler/feeds.py"
)

# 3. dashboard-code
Recreate-ConfigMap "dashboard-code" @("dashboard/app.py")

# 4. avro-schemas
Recreate-ConfigMap "avro-schemas" @(
    "schemas/news_raw.avsc",
    "schemas/news_processed.avsc"
)

# 5. airflow-dags (Source of truth for all DAGs)
Recreate-ConfigMap "airflow-dags" @(
    "airflow/dags/news_crawler_dag.py"
)

Write-Host "  ConfigMaps created!" -ForegroundColor Green

# Step 4: Deploy Core Infrastructure
Write-Host "`n[4/7] Deploying core infrastructure (Kafka, MongoDB, MinIO)..." -ForegroundColor White
kubectl apply -f "$K8sDir/01-kafka.yaml"
Write-Host "  Waiting 45s for Kafka to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 45
kubectl apply -f "$K8sDir/02-mongodb.yaml"
kubectl apply -f "$K8sDir/04-minio.yaml"
Start-Sleep -Seconds 15
Wait-ForPods "app=mongodb"
Write-Host "  Core infrastructure deployed!" -ForegroundColor Green

# Step 5: Deploy Processing and Serving Layer
Write-Host "`n[5/7] Deploying processing and serving layer (Spark, Trino, Grafana)..." -ForegroundColor White
kubectl apply -f "$K8sDir/03-spark.yaml"
kubectl apply -f "$K8sDir/05-trino.yaml"
kubectl apply -f "$K8sDir/06-grafana.yaml"
Wait-ForPods "app=spark-master"
Write-Host "  Processing and serving layer deployed!" -ForegroundColor Green

# Step 6: Deploy Applications
Write-Host "`n[6/7] Deploying applications (Crawler, Dashboard, Airflow, Alerts)..." -ForegroundColor White
kubectl apply -f "$K8sDir/07-crawler.yaml"
kubectl apply -f "$K8sDir/08-streamlit.yaml"
kubectl apply -f "$K8sDir/09-airflow.yaml"
kubectl apply -f "$K8sDir/19-alerts-deployment.yaml"
Wait-ForPods "app=streamlit-dashboard"
Write-Host "  Applications deployed!" -ForegroundColor Green

# Step 7: Deploy Processing Jobs
Write-Host "`n[7/7] Deploying processing jobs (Streaming and Batch)..." -ForegroundColor White
# ConfigMaps already created in Step 3.5

kubectl apply -f "$K8sDir/11-spark-streaming-job.yaml"
kubectl apply -f "$K8sDir/12-spark-batch-cronjob.yaml"
Write-Host "  Processing jobs deployed!" -ForegroundColor Green

# Full deployment: Run data ingestion and processing
# Full deployment: Trigger Airflow DAG
if ($Full) {
    Write-Host "`n[FULL] Triggering Airflow Batch Pipeline..." -ForegroundColor Cyan
    
    # Wait for Airflow to be definitely ready
    Wait-ForPods "app=airflow" 60
    
    # Unpause and Trigger
    try {
        $airflowPod = kubectl get pods -n news-pipeline -l app=airflow -o jsonpath="{.items[0].metadata.name}"
        if ($airflowPod) {
            Write-Host "  Triggering DAG on pod $airflowPod..." -ForegroundColor Yellow
            kubectl exec -n news-pipeline $airflowPod -- airflow dags unpause news_crawler_daily
            kubectl exec -n news-pipeline $airflowPod -- airflow dags trigger news_crawler_daily
            Write-Host "  Batch Pipeline triggered! Check Airflow UI." -ForegroundColor Green
        }
    }
    catch {
        Write-Host "  Failed to trigger Airflow automatically. Please do it manually." -ForegroundColor Red
    }
}

# Summary
Write-Host @"

=================================================================
  DEPLOYMENT COMPLETE!
=================================================================

Pod Status:
"@ -ForegroundColor Green

kubectl get pods -n news-pipeline --no-headers | ForEach-Object {
    $parts = $_ -split '\s+'
    $status = $parts[2]
    $icon = if ($status -eq "Running" -or $status -eq "Completed") { "[OK]" } else { "[..]" }
    Write-Host "  $icon $($parts[0]) - $status"
}

Write-Host @"

Access Services:
  Dashboard:  kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
              Then open: http://localhost:8501

  Grafana:    kubectl port-forward -n news-pipeline svc/grafana 3000:3000
              Then open: http://localhost:3000 (admin/admin)

  Trino:      kubectl port-forward -n news-pipeline svc/trino 8080:8080
              Then open: http://localhost:8080

  Airflow:    kubectl port-forward -n news-pipeline svc/airflow-webserver 8080:8080
              Then open: http://localhost:8080 (admin/admin)

  MongoDB:    kubectl port-forward -n news-pipeline svc/mongodb 27017:27017

Useful Commands:
  kubectl get pods -n news-pipeline              # View all pods
  kubectl logs -f deployment/XX -n news-pipeline # View logs
  kubectl get cronjobs -n news-pipeline          # View scheduled jobs
  minikube dashboard                             # Open K8s dashboard

"@ -ForegroundColor Cyan
