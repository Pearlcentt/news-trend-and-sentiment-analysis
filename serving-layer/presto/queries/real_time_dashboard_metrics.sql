-- Query: Aggregated metrics for real-time dashboard
-- Combines multiple real-time tables for comprehensive dashboard view

SELECT
  CURRENT_TIMESTAMP as query_time,
  COUNT(DISTINCT t.topic_token) as active_topics,
  SUM(t.article_count) as total_articles_recent,
  AVG(t.avg_sentiment) as overall_avg_sentiment,
  AVG(t.pos_share) as overall_pos_share,
  AVG(t.neg_share) as overall_neg_share,
  COUNT(DISTINCT s.source_domain) as active_sources,
  MAX(t.window_start_epoch) as latest_window_start,
  MAX(t.updated_at_epoch) as latest_update_time
FROM mongodb.news_rt.rt_trends t
CROSS JOIN mongodb.news_rt.rt_sentiment_by_source s
WHERE t.bucket_date = CURRENT_DATE
  AND t.window_start_epoch >= (unix_timestamp(current_timestamp) - 3600) * 1000
  AND s.bucket_date = CURRENT_DATE
  AND s.window_start_epoch >= (unix_timestamp(current_timestamp) - 3600) * 1000;

