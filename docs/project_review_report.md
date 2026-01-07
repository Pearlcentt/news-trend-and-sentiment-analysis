# Project Review Report

**News Trend & Sentiment Analysis System**  
_Lambda Architecture Big Data Pipeline_

---

## 1. Executive Summary

A production-grade **Big Data Pipeline** analyzing news trends and sentiment from 9 major English outlets. Built on Kubernetes using Lambda Architecture (Speed + Batch layers).

| Metric             | Value                         |
| ------------------ | ----------------------------- |
| **Manifests**      | 18 Kubernetes YAML files      |
| **Data Sources**   | 9 English news outlets        |
| **Articles/Year**  | ~18,000 (50/day × 365)        |
| **Categories**     | 8 classifications             |
| **Sentiment**      | 3-class (Pos/Neg/Neutral)     |
| **Quality Checks** | Great Expectations validation |

---

## 2. Architecture

### Lambda Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPEED LAYER (Real-time)                     │
│   [RSS Feeds] → [06-crawler] → [Kafka] → [12-spark-streaming]  │
│                                    ↓                            │
│                              [MongoDB rt_*]                     │
├─────────────────────────────────────────────────────────────────┤
│                     BATCH LAYER (Historical)                    │
│   [GDELT API] → [14-backfill] → [MongoDB] → [15-16-17-18 jobs] │
│                                    ↓                            │
│                              [HDFS Parquet]                     │
├─────────────────────────────────────────────────────────────────┤
│                     SERVING LAYER                               │
│   [MongoDB] + [HDFS] → [Trino SQL] → [Streamlit Dashboard]     │
└─────────────────────────────────────────────────────────────────┘
```

### Kubernetes Components

| Layer          | Components                                  |
| -------------- | ------------------------------------------- |
| **Messaging**  | Kafka, ZooKeeper, Schema Registry           |
| **Storage**    | MongoDB (hot), HDFS (cold), Cassandra (alt) |
| **Compute**    | Spark Master + Workers                      |
| **Serving**    | Trino, Grafana, Streamlit                   |
| **Scheduling** | Airflow                                     |

---

## 3. Complete Job Inventory

### Infrastructure Jobs (00-11)

| Job                     | Purpose                          |
| ----------------------- | -------------------------------- |
| `00-namespace`          | Create `news-pipeline` namespace |
| `01-kafka`              | Kafka + ZK + Schema Registry     |
| `02-mongodb`            | MongoDB deployment               |
| `03-spark`              | Spark Master + 2 Workers         |
| `04-trino`              | Trino SQL engine                 |
| `05-grafana`            | Monitoring dashboards            |
| `07-hdfs`               | HDFS NameNode + DataNode         |
| `08-cassandra`          | Cassandra cluster                |
| `10-airflow`            | Job scheduler                    |
| `11-persistent-volumes` | PVCs for data persistence        |

### Application Jobs (06, 09)

| Job            | Purpose                          |
| -------------- | -------------------------------- |
| `06-crawler`   | Continuous RSS → Kafka streaming |
| `09-streamlit` | Dashboard deployment             |

### Processing Jobs (12-18)

| Job                      | Purpose                       | Source Code                           |
| ------------------------ | ----------------------------- | ------------------------------------- |
| `12-spark-streaming`     | Real-time Kafka processing    | `jobs/streaming/spark_rt_pipeline.py` |
| `13-spark-batch`         | Daily HDFS batch writes       | `jobs/batch/spark_batch_pipeline.py`  |
| `14-fresh-crawler`       | One-shot RSS crawl            | Inline Python                         |
| `14-historical-backfill` | GDELT year backfill           | Inline Python                         |
| `15-process-historical`  | Sentiment analysis            | Inline Python (TextBlob)              |
| `16-classify-articles`   | Category classification       | Inline Python                         |
| `17-ml-training`         | ML model training             | `jobs/analytics/ml_pipeline.py`       |
| `18-data-quality`        | Great Expectations validation | `jobs/quality/great_expectations.py`  |

---

## 4. Data Quality Measures

### Filters Applied

| Filter           | Location    | Purpose                      |
| ---------------- | ----------- | ---------------------------- |
| English Domain   | 14-backfill | 9 trusted domains only       |
| English Language | Parser      | `language != 'english'` skip |
| 7-Day Filter     | 14-fresh    | Skip stale RSS articles      |
| HTML Stripping   | Dashboard   | Clean content display        |
| SSL Fix          | GDELT       | `verify=False` workaround    |

### Data Quality Job (18)

Validates:

- Required columns exist
- No null values in critical fields
- Article IDs are unique
- Sentiment values in valid set
- Minimum row count threshold

---

## 5. Analytics Capabilities

### Current (Integrated)

| Capability              | Job    | Method                |
| ----------------------- | ------ | --------------------- |
| Sentiment Analysis      | 15, 17 | TextBlob, Spark MLlib |
| Category Classification | 16     | Keyword frequency     |
| Data Validation         | 18     | Great Expectations    |

### Available (Reference Code)

| Capability            | File                                         | Method               |
| --------------------- | -------------------------------------------- | -------------------- |
| Graph Analytics       | `jobs/analytics/graph_analytics.py`          | PageRank, centrality |
| Time Series           | `jobs/analytics/time_series.py`              | Trend forecasting    |
| Advanced Aggregations | `jobs/analytics/spark_advanced_analytics.py` | Cube, rollup         |

---

## 6. How to Run

### Quick Start

```powershell
minikube start --memory=6144 --cpus=4
./deploy.ps1
kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
```

### Full Pipeline

```powershell
./deploy.ps1 -Full
```

Runs: Crawler → Sentiment → Classification → Data Quality

### Manual Job Execution

```powershell
# ML Training (requires substantial data)
kubectl apply -f k8s/17-ml-training-job.yaml

# Data Quality Check
kubectl apply -f k8s/18-data-quality-job.yaml
```

---

## 7. Testing

```powershell
pytest tests/ -v
```

| Test Type   | Location             | Coverage                         |
| ----------- | -------------------- | -------------------------------- |
| Unit        | `tests/unit/`        | Sentiment, HTML stripping, dates |
| Integration | `tests/integration/` | MongoDB operations               |

---

## 8. Future Roadmap

### High Priority (Recommended for Course) ✅ COMPLETE

| Feature                       | Description                                      | Status         |
| ----------------------------- | ------------------------------------------------ | -------------- |
| **Great Expectations Formal** | Full GE integration with checkpoints & data docs | ✅ Implemented |
| **Real-time Alerts**          | MongoDB-stored alerts for breaking news          | ✅ Implemented |
| **CI/CD with ArgoCD**         | GitOps automated deployments                     | ✅ Implemented |

### Medium Priority (Production)

| Feature               | Description                  | Benefit          |
| --------------------- | ---------------------------- | ---------------- |
| **Cloud Deployment**  | AWS EKS or Google GKE        | Real scalability |
| **LLM Summarization** | GPT/Claude article summaries | Better insights  |

### Low Priority (Optional)

| Feature                    | Description              | Benefit          |
| -------------------------- | ------------------------ | ---------------- |
| **Multi-language Support** | Non-English news sources | Broader coverage |

---

**Report Date**: 2025-12-31  
**Status**: ✅ COMPLETE (20 manifests, 17 Python files integrated)
