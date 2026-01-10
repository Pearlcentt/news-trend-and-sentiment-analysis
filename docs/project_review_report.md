# Project Review Report

**News Trend & Sentiment Analysis System**  
_Advanced Big Data Pipeline Course Project_

---

## 1. Executive Summary

We have successfully built and deployed a production-grade **Lambda Architecture** pipeline on Kubernetes. The system ingests, processes, and visualizes news data in real-time (Speed Layer) while maintaining a robust historical archive (Batch Layer).

| Metric           | Value                  | Note                     |
| :--------------- | :--------------------- | :----------------------- |
| **Architecture** | Lambda (Speed + Batch) | Fully decoupled layers   |
| **Deployment**   | Kubernetes (Minikube)  | ~20 Manifests, Helm-free |
| **Latency**      | < 60 Seconds           | For Real-Time Trends     |
| **History**      | Daily Updates          | Scheduled via Airflow    |
| **Data Sources** | 9 Major Outlets        | CNN, BBC, Reuters, etc.  |

---

## 2. Key Achievements

### ✅ 1. True Lambda Architecture

- **Speed Layer**: `Spark Structured Streaming` reads Kafka `news_raw` topic and updates MongoDB `news_rt` collection instantly.
- **Batch Layer**: `Spark Batch` (Airflow Scheduled) re-processes raw data nightly for high-accuracy Sentiment Analysis (TextBlob) and ML Classification (Logistic Regression).
- **Serving Layer**: A unified **Streamlit Dashboard** that seamlessly blends Real-Time (Hot) and Historical (Cold) data.

### ✅ 2. "Dual-Write" Batch Strategy

- **Problem**: Querying Parquet (Data Lake) from the dashboard was slow.
- **Solution**: The Batch Pipeline now writes to **two destinations**:
  1.  **HDFS/Parquet**: For long-term archival and data science (Training).
  2.  **MongoDB**: For low-latency dashboard queries.
- **Result**: Sub-second dashboard load times with full historical depth.

### ✅ 3. Automated Lifecycle (Self-Cleaning)

- **Feature**: Added a `cleanup_rt_data` task to the Daily Airflow DAG.
- **Logic**: Deletes Real-Time records older than **3 days**.
- **Impact**: Prevents storage bloat and keeps the "Speed Layer" lean, strictly adhering to Lambda Architecture principles (Speed layer is temporary).

### ✅ 4. Robust Operations

- **ConfigMap Deployment**: Python code (`app.py`, pipelines) is injected via ConfigMaps, allowing near-instant updates without rebuilding Docker images.
- **Resilience**: Airflow retries failed tasks; Spark Streaming checkpoints ensure exactly-once processing (mostly).

---

## 3. Technology Stack

| Layer         | Technologies                                       |
| :------------ | :------------------------------------------------- |
| **Ingestion** | Python Crawler, RSS, Kafka, Schema Registry (Avro) |
| **Speed**     | Spark Structured Streaming (PySpark), MongoDB      |
| **Batch**     | Apache Airflow, Spark Batch, HDFS (Parquet)        |
| **Serving**   | Streamlit, Trino (Optional), Grafana (Monitoring)  |
| **Infra**     | Kubernetes, Docker, Minikube                       |

---

## 4. Current Blockers & Risks

1.  **Minikube Resources**: The full stack requires ~8GB+ RAM. On smaller machines, pods may `CrashLoop`.
    - _Mitigation_: We scaled down `trino` and `cassandra` to prioritize the core pipeline.
2.  **Airflow DB Volatility**: Using SQLite in the dev container means DAG history is lost on pod restart.
    - _Mitigation_: Automated `airflow db migrate` commands in the deployment guide.
3.  **GDELT Data Quality**: Non-English articles occasionally slip through.
    - _Mitigation_: Added strict `language` filtering in the Crawler.

---

## 5. Future Roadmap (Post-Project)

- [ ] **Cloud Migration**: Move from Minikube to AWS EKS.
- [ ] **LLM Integration**: Replace `TextBlob` with `Llama3` or `GPT-4` for nuanced sentiment and 1-sentence summaries.
- [ ] **Vector Search**: Implement RAG (Retrieval-Augmented Generation) for "Ask my News" feature.

---

**Status**: 🟢 **READY FOR DEMO**  
**Last Updated**: 2026-01-10
