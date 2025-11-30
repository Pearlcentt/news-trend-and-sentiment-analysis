-- Query: Get detailed article information with current trend context
-- Useful for dashboard drill-downs showing article details within trending topics

SELECT
  e.article_id,
  e.title,
  e.source_domain,
  e.published_at,
  e.sentiment.label as sentiment_label,
  e.sentiment.polarity as sentiment_polarity,
  e.language,
  e.entities,
  e.keywords,
  t.topic_token,
  t.article_count as topic_article_count,
  t.avg_sentiment as topic_avg_sentiment,
  t.window_start_epoch,
  t.window_end_epoch
FROM hive.news_batch.articles_enriched_parquet e
LEFT JOIN mongodb.news_rt.rt_trends t
  ON contains(t.top_article_ids, e.article_id)
WHERE e.dt = CURRENT_DATE
  AND e.article_id = 'a1b2c3d4-0f3e-4d93-9d53-7c3f6a0c1a2b'  -- Example article_id
ORDER BY t.window_start_epoch DESC NULLS LAST;

