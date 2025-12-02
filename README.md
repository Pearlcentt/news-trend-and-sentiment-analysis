# 📰 News Trend & Sentiment Analysis Pipeline

## A production-ready **Lambda Architecture** implementation for real-time and batch processing of global news, deployed on **Kubernetes**. Built for the IT4931 Big Data Storage and Processing course at HUST.

## 🎯 Project Overview

This system provides:

- **Real-time news ingestion** from 14+ RSS feeds (BBC, CNN, Reuters, NYT, Guardian, etc.)
- **Sentiment analysis** on 10k+ articles (Positive| Negative| Neutral)
- **Category classification**
- **Interactive Streamlit dashboard** with content viewer

---

## 🏗️ Architecture

```
                            ┌─────────────────────────────────────────────────────┐
                            │                  DATA SOURCES                       │
                            │  BBC • CNN • Reuters • NYT • Guardian • GDELT API   │
                            └─────────────────────────┬───────────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               INGESTION LAYER                                           │
│  ┌──────────────┐    ┌─────────────────┐    ┌──────────────────────────────────────┐   │
│  │ News Crawler │───▶│ Kafka (Avro)    │───▶│ Schema Registry                      │   │
│  │ (RSS + API)  │    │ news-raw topic  │    │ Article schema validation            │   │
│  └──────────────┘    └─────────────────┘    └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                                      │
                    ┌─────────────────────────────────┼─────────────────────────────────┐
                    │                                 │                                 │
                    ▼                                 ▼                                 ▼
┌───────────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────┐
│      SPEED LAYER          │   │      BATCH LAYER          │   │    SERVING LAYER      │
│  Spark Structured         │   │  Spark Batch Jobs         │   │  Trino (SQL)          │
│  Streaming                │   │  - Sentiment Analysis     │   │  Federated queries    │
│  - Real-time aggregates   │   │  - Category Classification│   │  across all stores    │
│  - 5-min windows          │   │  - Keyword Extraction     │   │                       │
└───────────────────────────┘   └───────────────────────────┘   └───────────────────────┘
                    │                                 │                                 │
                    ▼                                 ▼                                 │
┌───────────────────────────┐   ┌───────────────────────────┐                           │
│  MongoDB (Hot Storage)    │   │  HDFS + Parquet           │◀──────────────────────────┘
│  - Real-time views        │   │  (Cold Storage)           │
│  - 4,784+ articles        │   │  - Historical archive     │
└───────────────────────────┘   └───────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           VISUALIZATION LAYER                                           │
│  ┌────────────────────────────────────────────────────────────────────────────────┐    │
│  │  Streamlit Dashboard (Light Theme)                                              │    │
│  │  📊 Sentiment Distribution | 🌐 Top Sources | 📁 Categories                     │    │
│  │  📈 Timeline | 🔑 Keywords | 🌍 Locations | 📰 News Feed                        │    │
│  └────────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────────┘

```

## 🔧 Port Configuration

| Service       | Internal | NodePort | Access            |
| ------------- | -------- | -------- | ----------------- |
| **Streamlit** | 8501     | 30501    | `localhost:8501`  |
| **MongoDB**   | 27017    | 30017    | `localhost:27017` |
| **Grafana**   | 3000     | 30300    | `localhost:3000`  |
| **Airflow**   | 8080     | 30080    | `localhost:8080`  |
| Kafka         | 9092     | -        | Internal          |
| Spark Master  | 7077     | -        | Internal          |

---

## 🎨 Dashboard Features

- **Sentiment Distribution** - Pie chart with color coding
- **Top Sources** - News source breakdown
- **Category Distribution** - Donut chart by topic
- **Timeline** - News volume over time
- **Keywords Treemap** - Trending terms
- **Locations Chart** - Geographic mentions
- **Word Cloud** - Visual term frequency
- **Sentiment Trend** - 100% stacked bar over time
- **News Feed** - Articles with expandable content viewer

## 📝 Course Information

**Course**: IT4931 - Big Data Storage and Processing  
**Institution**: HUST - Hanoi University of Science and Technology  
**Year**: 2025

---

## 📄 License

MIT License
