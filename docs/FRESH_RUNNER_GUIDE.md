# 🚀 Fresh Runner Guide

**Get real news data flowing in minutes.**

This guide helps you run the **authentic** News Trend & Sentiment Analysis pipeline with real English news from major outlets.

---

## 📐 Architecture Overview

This system uses **Lambda Architecture** with two parallel data flows:

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA INGESTION                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [06-crawler.yaml]           [14-fresh/historical-job.yaml]    │
│  Streaming Layer             Batch Layer                       │
│  ├─ Runs 24/7               ├─ One-shot jobs                   │
│  ├─ Pushes to Kafka         ├─ Writes directly to MongoDB      │
│  └─ Real-time updates       └─ Historical backfill             │
│                                                                 │
│  Airflow schedules batch jobs daily at 6 AM                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Component             | File                                  | Purpose                         |
| --------------------- | ------------------------------------- | ------------------------------- |
| **Streaming Crawler** | `k8s/06-crawler.yaml`                 | Continuous RSS crawling → Kafka |
| **Fresh RSS Job**     | `k8s/14-fresh-crawler-job.yaml`       | One-shot recent news (7 days)   |
| **Historical Job**    | `k8s/14-historical-backfill-job.yaml` | GDELT backfill (full year)      |
| **Airflow DAG**       | `airflow/dags/news_crawler_dag.py`    | Schedules daily batch jobs      |

---

## ⚡ Quick Start

### 1. Start Minikube

```powershell
minikube start --memory=6144 --cpus=4
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/11-persistent-volumes.yaml
```

### 2. Deploy Pipeline

```powershell
./deploy.ps1
```

_Wait 2-3 minutes for pods to reach `Running` state._

### 3. Ingest Data

**Option A: Fresh News (Quick Start)**

```powershell
kubectl apply -f k8s/14-fresh-crawler-job.yaml
```

**Option B: Historical Backfill (Full Year)**

```powershell
kubectl apply -f k8s/14-historical-backfill-job.yaml
```

> **Data Sources**: BBC, CNN, Guardian, Reuters, NPR, Fox News, NYT, WaPo, AP News  
> **Filter**: English-only (50 articles/day)

### 4. Process Data

```powershell
kubectl apply -f k8s/15-process-historical-job.yaml   # Sentiment
kubectl apply -f k8s/16-classify-articles-job.yaml    # Categories
kubectl apply -f k8s/18-data-quality-job.yaml         # Data Quality Validation
```

### 5. Access Dashboard

```powershell
kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
```

> Open: [http://localhost:8501](http://localhost:8501)

---

## 🔄 Scheduled Crawling (Airflow)

For automated daily crawling, use Airflow:

```powershell
cd airflow
docker-compose up -d
```

Access Airflow UI: [http://localhost:8080](http://localhost:8080) (admin/admin)

The `news_crawler_daily` DAG runs at 6 AM and:

1. Crawls fresh RSS news
2. Processes sentiment
3. Classifies categories

---

## ✨ Dashboard Features

| Feature                 | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| **Full Article Reader** | Complete content, HTML stripped, no truncation                           |
| **Published Dates**     | Uses original article date (not crawl time)                              |
| **English Only**        | All data filtered to English sources                                     |
| **Real-Time Trends**    | Speed Layer shows last 3 days                                            |
| **8 Categories**        | Politics, Tech, Business, Entertainment, Sports, Science, World, General |

---

## 💾 Data Management

### Backup

```powershell
./scripts/backup_data.ps1
```

### Restore

```powershell
kubectl cp backup.json news-pipeline/<mongodb-pod>:/tmp/data.json
kubectl exec -n news-pipeline deployment/mongodb -- mongoimport \
  --db news_analytics --collection historical_articles \
  --file /tmp/data.json --jsonArray --upsert
```

---

## 🧪 Testing

```powershell
# Run all tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v
```

---

## 🛠️ Troubleshooting

| Problem                | Solution                      |
| ---------------------- | ----------------------------- |
| Dashboard empty        | Run crawler + processing jobs |
| GDELT SSL error        | Fixed in code (verify=False)  |
| Non-English articles   | Language filter active        |
| Old dates (April 2023) | 7-day date filter active      |

---

## 📋 Quick Reference

```powershell
# Check pods
kubectl get pods -n news-pipeline

# View crawler logs
kubectl logs -f job/historical-backfill-jan2025 -n news-pipeline

# Restart dashboard
kubectl delete pod -n news-pipeline -l app=streamlit-dashboard

# Stop backfill job
kubectl delete job historical-backfill-jan2025 -n news-pipeline
```

---

**Last Updated**: 2025-12-31
