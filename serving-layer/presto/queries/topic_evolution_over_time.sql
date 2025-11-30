-- Query: Track topic evolution combining real-time windows with historical data
-- Shows how topics are trending over different time windows

WITH recent_trends AS (
  SELECT
    topic_token,
    window_start_epoch,
    window_end_epoch,
    article_count,
    avg_sentiment,
    pos_share,
    neg_share
  FROM mongodb.news_rt.rt_trends
  WHERE bucket_date = CURRENT_DATE
    AND window_start_epoch >= (unix_timestamp(current_timestamp) - 7200) * 1000  -- Last 2 hours
),
historical_topics AS (
  SELECT
    topic_token,
    DATE(published_at) as topic_date,
    COUNT(*) as article_count,
    AVG(sentiment.polarity) as avg_sentiment,
    SUM(CASE WHEN sentiment.label = 'pos' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as pos_share,
    SUM(CASE WHEN sentiment.label = 'neg' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as neg_share
  FROM hive.news_batch.articles_enriched_parquet
  CROSS JOIN UNNEST(topics) AS t(topic)
  WHERE dt >= DATE_FORMAT(DATE_ADD('day', -30, CURRENT_DATE), '%Y-%m-%d')
    AND t.topic.topic_id IS NOT NULL
  GROUP BY topic_token, DATE(published_at)
)
SELECT
  COALESCE(r.topic_token, h.topic_token) as topic_token,
  r.article_count as recent_count,
  r.avg_sentiment as recent_sentiment,
  h.article_count as historical_count,
  h.avg_sentiment as historical_sentiment,
  (r.article_count * 1.0 / NULLIF(h.article_count, 0)) as growth_factor
FROM recent_trends r
FULL OUTER JOIN historical_topics h
  ON r.topic_token = h.topic_token
WHERE r.article_count > 10 OR h.article_count > 50
ORDER BY r.article_count DESC NULLS LAST
LIMIT 50;

