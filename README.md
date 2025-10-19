# 📰 Real-Time Global News Trend & Sentiment Analytics Platform

![Architecture Banner](https://img.shields.io/badge/Architecture-Lambda-orange?style=for-the-badge)
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-000000.svg?style=for-the-badge&logo=apachekafka&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Apache%20Spark-%23E25A1C.svg?style=for-the-badge&logo=apachespark&logoColor=white)
![Cassandra](https://img.shields.io/badge/Apache%20Cassandra-1287B1.svg?style=for-the-badge&logo=apachecassandra&logoColor=white)
![Presto](https://img.shields.io/badge/Presto-5A2D81.svg?style=for-the-badge&logo=prestodb&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5.svg?style=for-the-badge&logo=kubernetes&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)

---

## 🧩 Problem Definition

### 🗞️ Selected Problem
This project develops a **real-time global news trend and sentiment analytics system** that continuously ingests and processes online news streams from publishers such as **Reuters**, **The Irish Times**, and **The Wall Street Journal**.  
The platform supports both **historical batch analysis** and **real-time stream analytics** to answer critical questions like:

- What global topics are trending right now?  
- How is public sentiment evolving around key themes (e.g., elections, markets, disasters)?  
- Which regions or publishers show the strongest sentiment shifts?

---

### 🌍 Suitability for Big Data
The system demonstrates all **five Vs** of big data:

| 💡 Aspect | 📰 In this Project |
|------------|-------------------|
| **Volume** | Thousands of news articles per hour across multiple publishers |
| **Velocity** | Real-time streams updated every few seconds |
| **Variety** | Structured (metadata), semi-structured (JSON), and unstructured (article text) |
| **Veracity** | Duplicate or inconsistent articles require cleaning & deduplication |
| **Value** | Enables actionable insights on emerging topics and sentiment shifts |

Thus, this problem perfectly fits the **Lambda Architecture**, combining **batch** and **speed** layers for both historical and real-time analytics.

---

### ⚙️ Scope and Limitations

**Scope**
- Real-time ingestion of global news feeds via APIs/RSS  
- Stream processing for trending topics & sentiment detection  
- Historical batch processing for long-term trend discovery  
- Distributed data storage in HDFS and NoSQL databases  
- Visualization dashboard for interactive insights  

**Limitations**
- Dependent on external API rate limits and feed availability  
- Focused primarily on English-language publishers  
- Predictive modeling (e.g., trend forecasting) is future work  

---

## 🏗️ Architecture and Design

### 🧠 Overall Architecture
We adopt a **Lambda Architecture**, combining **batch processing** for historical analytics with **streaming processing** for low-latency insights.  
This hybrid approach ensures both accuracy and freshness in analytics.

📊 **Layer Overview**

1. **Data Ingestion Layer** → Collects live news via APIs and streams to Kafka topics  
2. **Speed Layer** → Spark Structured Streaming performs near-real-time sentiment & topic aggregation  
3. **Batch Layer** → Spark Batch jobs process and store large-scale historical data in HDFS  
4. **Storage Layer** → Cassandra/MongoDB (hot data), HDFS (cold data)  
5. **Query Layer** → Presto enables unified SQL access across data stores  
6. **Visualization Layer** → Dashboards (Grafana/Kibana/React) present insights interactively  
7. **Deployment Layer** → Kubernetes orchestrates scalable, fault-tolerant microservices  

<p align="center">
  <img src="https://cdn-images-1.medium.com/max/800/1*I34tYZreUmLBpp97noHjxQ.png" alt="Lambda Architecture Diagram" width="500"/>
</p>

---

### 🧩 Detailed Components and Roles

| 🧱 Component | 🛠️ Technology | 🎯 Role |
|--------------|----------------|--------|
| **Data Source** | Reuters, WSJ, Irish Times APIs | Provide global live news streams |
| **Ingestion** | Apache Kafka | Streams data into topics `news_raw`, `news_processed` |
| **Batch Layer** | Apache Spark (Batch) + HDFS | Historical sentiment modeling and topic detection |
| **Speed Layer** | Spark Structured Streaming | Real-time trend and sentiment updates |
| **Storage (Hot)** | MongoDB / Cassandra | Stores latest processed results for dashboards |
| **Storage (Cold)** | HDFS | Archives all raw and processed data |
| **Query Layer** | Presto | Unified SQL queries across batch and real-time data |
| **Visualization** | Grafana / Kibana / React | Dashboards showing sentiment and topic evolution |
| **Deployment** | Kubernetes | Container orchestration and scalability |

---

### 🔁 Data Flow Overview

```text
[News APIs / RSS Feeds]
     ↓
[Kafka Producers] → publish to → [Kafka Topics: news_raw, news_processed]
     ↓
 ┌─────────────┬──────────────────┐
 │             │                  │
 │     [Spark Structured Streaming] (Speed Layer)
 │             │                  │
 │             └──→ [Cassandra] (Hot Data)
 │
 └──→ [Spark Batch + HDFS] (Batch Layer)
       ↓
     [Presto Engine] → Unified Query Layer
       ↓
 [Visualization Dashboard]
```

### 🧭 Key Advantages

* Unified Lambda Architecture for historical and real-time analytics
* Scalable ingestion from multiple news publishers
* Low-latency detection of emerging topics and sentiments
* Modular and containerized design for deployment flexibility
