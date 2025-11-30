-- Query: Trending topics now with historical context
-- Combines real-time trends (MongoDB) with detailed article data (HDFS)
-- This is the main query from the requirements document

SELECT
  t.topic_token,
  t.article_count,
  t.avg_sentiment,
  t.pos_share,
  t.neg_share,
  t.unique_sources,
  e.title,
  e.source_domain,
  e.published_at,
  e.sentiment.label as article_sentiment_label,
  e.sentiment.polarity as article_sentiment_polarity,
  e.language
FROM mongodb.news_rt.rt_trends t                              -- NoSQL catalog (speed layer)
JOIN hive.news_batch.articles_enriched_parquet e             -- HDFS catalog (batch layer)
  ON contains(t.top_article_ids, e.article_id)
WHERE t.bucket_date = DATE '2025-10-27'
  AND t.window_start_epoch >= (unix_timestamp(current_timestamp) - 3600) * 1000
  AND e.dt = '2025-10-27'
ORDER BY t.article_count DESC
LIMIT 20;

