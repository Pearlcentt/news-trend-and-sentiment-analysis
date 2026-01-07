# Trino Kafka Queries for news_processed Topic

This document provides sample queries for accessing the `news_processed` Kafka topic through Trino.

## Prerequisites

1. Deploy updated Trino manifest:

   ```powershell
   kubectl apply -f k8s/04-trino.yaml
   ```

2. Port-forward Trino service:

   ```powershell
   kubectl port-forward -n news-pipeline svc/trino 8080:8080
   ```

3. Connect via Trino CLI or DBeaver to `localhost:8080`

## Available Catalogs

| Catalog   | Description                       |
| --------- | --------------------------------- |
| `mongodb` | MongoDB news_analytics database   |
| `kafka`   | Kafka topics with Schema Registry |
| `tpch`    | TPC-H benchmark data              |

## news_processed Topic Schema

The `news_processed` topic contains enriched articles from the streaming job:

| Field                | Type    | Description                    |
| -------------------- | ------- | ------------------------------ |
| `article_id`         | VARCHAR | Unique article ID              |
| `source_domain`      | VARCHAR | News source domain             |
| `published_at`       | BIGINT  | Publication timestamp (ms)     |
| `language`           | VARCHAR | Article language               |
| `sentiment.label`    | VARCHAR | Sentiment (pos/neu/neg)        |
| `sentiment.polarity` | DOUBLE  | Sentiment score (-1 to 1)      |
| `keywords`           | ARRAY   | Extracted keywords with scores |
| `entities`           | ARRAY   | Named entities                 |
| `topics`             | ARRAY   | Topic IDs                      |
| `clean_text`         | VARCHAR | Processed article text         |

## Sample Queries

### List Available Topics

```sql
SHOW TABLES FROM kafka.news_pipeline;
```

### Query Latest Articles

```sql
SELECT
    article_id,
    source_domain,
    from_unixtime(published_at / 1000) as published_time,
    element_at(sentiment, 'label') as sentiment_label,
    element_at(sentiment, 'polarity') as sentiment_score
FROM kafka.news_pipeline.news_processed
LIMIT 100;
```

### Aggregate Sentiment by Source

```sql
SELECT
    source_domain,
    COUNT(*) as article_count,
    AVG(CAST(element_at(sentiment, 'polarity') AS DOUBLE)) as avg_sentiment
FROM kafka.news_pipeline.news_processed
GROUP BY source_domain
ORDER BY article_count DESC
LIMIT 20;
```

### Query with MongoDB Join

```sql
-- Join Kafka real-time data with MongoDB historical data
SELECT
    k.article_id,
    k.source_domain,
    element_at(k.sentiment, 'label') as rt_sentiment,
    m.category
FROM kafka.news_pipeline.news_processed k
LEFT JOIN mongodb.news_analytics.historical_articles m
    ON k.article_id = m.article_id
LIMIT 50;
```

### Extract Top Keywords

```sql
SELECT
    source_domain,
    transform(keywords, x -> element_at(x, 'term')) as top_terms
FROM kafka.news_pipeline.news_processed
WHERE cardinality(keywords) > 0
LIMIT 20;
```

## Troubleshooting

### Topic Not Found

Ensure the streaming job is running and producing to `news_processed`:

```powershell
kubectl logs deployment/spark-streaming-job -n news-pipeline
```

### Schema Registry Connection

Verify Schema Registry is accessible:

```powershell
kubectl exec -n news-pipeline deployment/trino -- \
    curl -s http://sr-service:8081/subjects
```
