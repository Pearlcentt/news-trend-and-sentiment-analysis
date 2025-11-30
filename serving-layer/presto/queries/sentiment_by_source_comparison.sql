-- Query: Compare real-time sentiment by source with historical averages
-- Shows current sentiment trends vs historical patterns

WITH realtime_sentiment AS (
  SELECT
    source_domain,
    bucket_date,
    window_start_epoch,
    article_count as rt_article_count,
    avg_sentiment as rt_avg_sentiment,
    updated_at_epoch
  FROM mongodb.news_rt.rt_sentiment_by_source
  WHERE bucket_date = CURRENT_DATE
    AND window_start_epoch >= (unix_timestamp(current_timestamp) - 3600) * 1000
),
historical_avg AS (
  SELECT
    source_domain,
    dt,
    AVG(sentiment.polarity) as hist_avg_sentiment,
    COUNT(*) as hist_article_count
  FROM hive.news_batch.articles_enriched_parquet
  WHERE dt >= DATE_FORMAT(DATE_ADD('day', -7, CURRENT_DATE), '%Y-%m-%d')
  GROUP BY source_domain, dt
)
SELECT
  r.source_domain,
  r.rt_article_count,
  r.rt_avg_sentiment,
  h.hist_avg_sentiment,
  (r.rt_avg_sentiment - h.hist_avg_sentiment) as sentiment_delta,
  h.hist_article_count
FROM realtime_sentiment r
LEFT JOIN historical_avg h
  ON r.source_domain = h.source_domain
ORDER BY ABS(sentiment_delta) DESC;

