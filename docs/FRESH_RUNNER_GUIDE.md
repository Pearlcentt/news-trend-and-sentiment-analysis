# 🚀 Fresh Runner Guide

**Get the News Trend & Sentiment Analysis Pipeline running in 5 minutes.**

---

## 🏗️ Architecture Summary

This system implements a **Lambda Architecture** on Kubernetes:

1.  **Speed Layer (Real-Time)**: Kafka -> Spark Streaming -> MongoDB (Hot) -> Dashboard.
2.  **Batch Layer (Historical)**: Airflow (Daily @ 6 PM) -> Spark Batch -> HDFS (Cold) + MongoDB (Serving) -> Dashboard.
3.  **Serving Layer**: Streamlit Dashboard + Trino.

---

## ⚡ Quick Start

### 1. Prerequisites

- **Minikube** (installed and running)
- **Kubectl**
- **PowerShell** (Recommended for Windows)

### 2. One-Click Deployment

We have consolidated all deployment logic into a robust PowerShell script.

```powershell
# Run the deployment script
./deploy.ps1
```

**What this script does:**

1.  Checks prerequisites.
2.  starts Minikube (if stopped).
3.  Deploys Core Infra (Kafka, MongoDB, Spark, HDFS).
4.  Generates **ConfigMaps** (syncs Python code to K8s).
5.  Deploys Apps (Crawler, Dashboard, Airflow, Streaming Job).

_Wait ~3-5 minutes for all pods to show `Running`._

---

## 🖥️ Accessing Interfaces

Once deployed, access the services via Port-Forwarding:

### 📊 Main Dashboard

```powershell
kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
```

> **URL**: [http://localhost:8501](http://localhost:8501)

### 🌪️ Airflow (Batch Orchestration)

```powershell
kubectl port-forward -n news-pipeline svc/airflow-webserver 8080:8080
```

> **URL**: [http://localhost:8080](http://localhost:8080)  
> **Creds**: `admin` / `admin`

### 🔎 Spark UI (Monitoring)

```powershell
kubectl port-forward -n news-pipeline svc/spark-master 8090:8080
```

> **URL**: [http://localhost:8090](http://localhost:8090)

---

## 🎮 Operations Guide

### 1. Trigger Batch Processing (Historical Data)

The batch job runs automatically at **6:00 PM** daily. To trigger it manually (e.g., for a demo):

```powershell
# Unpause and Trigger DAG
kubectl exec -n news-pipeline deployment/airflow -- airflow dags unpause news_crawler_daily
kubectl exec -n news-pipeline deployment/airflow -- airflow dags trigger news_crawler_daily
```

**What happens:**

- Crawls fresh news (past 7 days).
- Runs Sentiment Analysis & ML Classification.
- Backfills `news_analytics.historical_articles`.
- Updates the "Articles" tab in the Dashboard.

### 2. Real-Time Data

- **Status**: Running automatically (`spark-streaming-job`).
- **Verify**: Check "Real-Time Trends" in the Dashboard.
- **Cleanup**: Data older than 3 days is auto-deleted by Airflow to save space.

### 3. Update Code (Hot Reload)

If you edit `app.py`, `streaming_pipeline.py`, or `batch_pipeline.py`, apply changes without rebuilding Docker images:

```powershell
# Re-run deployment script to update ConfigMaps
./deploy.ps1
# OR manually:
./k8s/create-configmaps.sh
```

Then restart the relevant pods:

```powershell
kubectl delete pod -n news-pipeline -l app=streamlit-dashboard
# OR
kubectl delete pod -n news-pipeline -l app=spark-streaming-job
```

---

## 🛠️ Troubleshooting

| Issue                       | Solution                                                                 |
| --------------------------- | ------------------------------------------------------------------------ |
| **Dashboard shows "???"**   | Browser/Docker encoding issue. Fixed in latest build (UTF-8).            |
| **Airflow "Dag Not Found"** | `kubectl exec -n news-pipeline deployment/airflow -- airflow db migrate` |
| **Pods Pending**            | Check resources: `minikube start --memory=8192 --cpus=4`                 |
| **No Real-Time Data**       | Restart streaming: `kubectl delete pod -l app=spark-streaming-job`       |

---

## 🧹 Factory Reset (Teardown)

To completely wipe the environment and start fresh (simulate a new machine):

```powershell
# 1. Delete Minikube Cluster (Removes all data/volumes)
minikube delete --all --purge

# 2. (Optional) Prune Docker Resources
# WARNING: This deletes ALL Docker images/containers, not just for this project
docker system prune -a --volumes -f

# 3. Clear local temporary config
Remove-Item -Path $env:USERPROFILE\.kube -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $env:USERPROFILE\.minikube -Recurse -Force -ErrorAction SilentlyContinue
```

---

**Last Updated**: 2026-01-10
