# Architecture Overview

## Lambda Architecture for News Trend & Sentiment Analysis

This document describes the full Lambda Architecture implementation with speed, batch, and serving layers.

---

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Sources["📰 Data Sources"]
        RSS[RSS Feeds]
        API[News APIs]
    end

    subgraph Ingestion["📤 Ingestion Layer"]
        Crawler[News Crawler]
        SR[Schema Registry]
        Kafka[Apache Kafka<br/>news_raw topic]
    end

    subgraph Processing["⚡ Processing Layer"]
        subgraph Speed["Speed Layer"]
            SS[Spark Structured<br/>Streaming]
        end
        subgraph Batch["Batch Layer"]
            SB[Spark Batch<br/>Jobs]
        end
    end

    subgraph Storage["💾 Storage Layer"]
        MongoDB[(MongoDB<br/>Hot Data)]
        HDFS[(HDFS<br/>Parquet Files)]
    end

    subgraph Serving["🔍 Serving Layer"]
        Trino[Trino SQL]
    end

    subgraph Visualization["📊 Visualization"]
        Grafana[Grafana<br/>Dashboards]
    end

    RSS --> Crawler
    API --> Crawler
    Crawler --> SR
    SR --> Kafka
    Kafka --> SS
    Kafka --> SB
    SS --> MongoDB
    SB --> HDFS
    MongoDB --> Trino
    HDFS --> Trino
    Trino --> Grafana
```

---

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant RSS as RSS Feeds
    participant Crawler as News Crawler
    participant Kafka as Kafka
    participant Speed as Speed Layer
    participant Batch as Batch Layer
    participant Mongo as MongoDB
    participant HDFS as HDFS
    participant Trino as Trino
    participant User as Dashboard

    RSS->>Crawler: HTTP GET (feedparser)
    Crawler->>Kafka: Produce (Avro + Schema Registry)

    par Real-time Path
        Kafka->>Speed: Consume (Structured Streaming)
        Speed->>Mongo: Write aggregates (foreachBatch)
        Mongo->>Trino: SQL Query
    and Historical Path
        Kafka->>Batch: Read all (spark.read)
        Batch->>HDFS: Write Parquet (partitioned)
        HDFS->>Trino: SQL Query
    end

    Trino->>User: Visualization
```

---

## Component Details

### Data Ingestion Layer

| Component       | Technology          | Purpose                           |
| --------------- | ------------------- | --------------------------------- |
| Crawler         | Python + feedparser | Fetch RSS feeds, parse articles   |
| Schema Registry | Confluent           | Avro schema management, evolution |
| Kafka           | Apache Kafka 7.4    | Message queue, news_raw topic     |

**Key Features:**

- Avro serialization with schema versioning
- Content hashing (MD5, simhash64) for deduplication
- Per-source rate limiting

### Speed Layer (Real-time)

| Component     | Technology                 | Purpose                |
| ------------- | -------------------------- | ---------------------- |
| Streaming Job | Spark Structured Streaming | Low-latency processing |
| Hot Storage   | MongoDB                    | Real-time aggregates   |

**Key Features:**

- **Auto-Categorization**: Lightweight UDF for keyword-based topic assignment.
- **Latency**: ~60 seconds end-to-end.
- **Lifecycle**: Automated cleanup of data > 3 days old via Airflow.
- **Output**: `news_rt` database (Trends, Source Sentiment).

### Batch Layer (Historical)

| Component     | Technology         | Purpose                    |
| ------------- | ------------------ | -------------------------- |
| Scheduler     | Apache Airflow 2.7 | Daily Orchestration (6 PM) |
| Batch Job     | Spark Batch        | Historical processing      |
| Cold Storage  | HDFS + Parquet     | Long-term Archive          |
| Serving Store | MongoDB            | Dashboard Integration      |

**Key Features:**

- **Dual-Write Strategy**:
  1.  **Parquet (HDFS)**: Optimized for heavy queries/retraining.
  2.  **MongoDB**: Optimized for Dashboard display (Collections: `historical_articles`).
- **Schedule**: Runs daily at **18:00 (6 PM)**.
- **Logic**: Deduplicates against existing data using content hash.

**Advanced Analytics:**

- MLlib sentiment classification (TF-IDF + LogisticRegression)
- GraphFrames entity analysis (PageRank, connected components)
- Time series analysis (rolling windows, anomaly detection)

### Serving Layer

| Component     | Technology | Purpose               |
| ------------- | ---------- | --------------------- |
| Query Engine  | Trino      | Federated SQL queries |
| Visualization | Grafana    | Real-time dashboards  |

**Key Features:**

- Unified SQL access to MongoDB + HDFS
- Low-latency queries for dashboards
- Historical analysis across all data

---

## Kubernetes Deployment

```mermaid
graph TB
    subgraph K8s["Kubernetes Cluster (news-pipeline namespace)"]
        subgraph Messaging
            ZK[Zookeeper Pod]
            KF[Kafka Pod]
            SR[Schema Registry Pod]
        end

        subgraph Compute
            SM[Spark Master]
            SW1[Spark Worker 1]
            SW2[Spark Worker 2]
        end

        subgraph Storage
            MG[MongoDB Pod]
            HD[HDFS NameNode]
            DN[HDFS DataNodes]
        end

        subgraph Serving
            TR[Trino Pod]
            GF[Grafana Pod]
        end

        subgraph Apps
            CR[Crawler Pod]
        end
    end

    ZK --> KF
    KF --> SR
    CR --> KF
    KF --> SM
    SM --> SW1
    SM --> SW2
    SW1 --> MG
    SW1 --> HD
    SW2 --> MG
    SW2 --> HD
    HD --> DN
    MG --> TR
    HD --> TR
    TR --> GF
```

### ArgoCD CI/CD

GitOps deployment configuration in `argocd/`:

- `application.yaml` - ArgoCD Application with auto-sync and health checks
- `README.md` - Setup and usage instructions

## Data Schema

### news_raw (Kafka Topic)

```json
{
  "article_id": "uuid",
  "source_domain": "reuters.com",
  "title": "Article title",
  "body_text": "Full article content...",
  "published_at": 1705334400000,
  "language": "en",
  "tags": ["economy", "markets"],
  "content_hash_md5": "abc123...",
  "event_time": 1705334400000
}
```

### Processed Schema (Speed Layer Output)

```json
{
  "article_id": "uuid",
  "source_domain": "reuters.com",
  "sentiment": { "label": "pos", "polarity": 0.15 },
  "keywords": [{ "term": "market", "score": 0.25 }],
  "entities": [{ "type": "ORG", "text": "Reuters", "norm": "reuters" }],
  "topics": [{ "topic_id": 42, "score": 0.3 }]
}
```

---

## Performance Considerations

| Aspect              | Configuration                          |
| ------------------- | -------------------------------------- |
| Shuffle Partitions  | 200 (default), AQE adjusts dynamically |
| Broadcast Threshold | 64 MB                                  |
| Watermark           | 30 minutes                             |
| Window Duration     | 10 minutes                             |
| Window Slide        | 5 minutes                              |
| Parquet Compression | Snappy                                 |
| Bucketing           | 16 buckets on source_domain            |

---

## Monitoring

- **Spark UI**: Job progress, DAG visualization, executor metrics
- **Grafana**: Real-time dashboards for trends, sentiment
- **Kafka**: Consumer lag, partition status
- **MongoDB**: Collection stats, query performance

---

## References

- [Apache Spark Documentation](https://spark.apache.org/docs/latest/)
- [Kafka Documentation](https://kafka.apache.org/documentation/)
- [Lambda Architecture](https://www.databricks.com/glossary/lambda-architecture)
- IT4931 Lab Materials (spark-lab, Streaming_Lakehouse_lab)
