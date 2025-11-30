#!/usr/bin/env python3
"""
Example Python client for querying Presto serving layer
Demonstrates how to connect to Presto and execute queries programmatically
"""

import pyhive.presto
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime, timedelta


class PrestoNewsClient:
    """Client for querying news analysis data via Presto"""
    
    def __init__(self, host: str = 'localhost', port: int = 8080):
        """
        Initialize Presto connection
        
        Args:
            host: Presto coordinator host
            port: Presto HTTP port (default 8080)
        """
        self.connection = pyhive.presto.connect(
            host=host,
            port=port,
            protocol='http'
        )
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute a SQL query and return results as pandas DataFrame
        
        Args:
            query: SQL query string
            
        Returns:
            pandas DataFrame with query results
        """
        return pd.read_sql(query, self.connection)
    
    def get_trending_topics(self, hours: int = 1, limit: int = 20) -> pd.DataFrame:
        """
        Get trending topics with article details (main dashboard query)
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of results
            
        Returns:
            DataFrame with trending topics and article details
        """
        cutoff_epoch = int((datetime.utcnow() - timedelta(hours=hours)).timestamp() * 1000)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        query = f"""
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
          e.sentiment.polarity as article_sentiment_polarity
        FROM mongodb.news_rt.rt_trends t
        JOIN hive.news_batch.articles_enriched_parquet e
          ON contains(t.top_article_ids, e.article_id)
        WHERE t.bucket_date = DATE '{today}'
          AND t.window_start_epoch >= {cutoff_epoch}
          AND e.dt = '{today}'
        ORDER BY t.article_count DESC
        LIMIT {limit}
        """
        
        return self.execute_query(query)
    
    def get_sentiment_by_source(self, hours: int = 1) -> pd.DataFrame:
        """
        Get real-time sentiment by source
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            DataFrame with sentiment metrics by source
        """
        cutoff_epoch = int((datetime.utcnow() - timedelta(hours=hours)).timestamp() * 1000)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        query = f"""
        SELECT
          source_domain,
          article_count,
          avg_sentiment,
          updated_at_epoch
        FROM mongodb.news_rt.rt_sentiment_by_source
        WHERE bucket_date = DATE '{today}'
          AND window_start_epoch >= {cutoff_epoch}
        ORDER BY article_count DESC
        """
        
        return self.execute_query(query)
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated metrics for dashboard overview
        
        Returns:
            Dictionary with dashboard metrics
        """
        cutoff_epoch = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        query = f"""
        SELECT
          COUNT(DISTINCT t.topic_token) as active_topics,
          SUM(t.article_count) as total_articles_recent,
          AVG(t.avg_sentiment) as overall_avg_sentiment,
          AVG(t.pos_share) as overall_pos_share,
          AVG(t.neg_share) as overall_neg_share,
          COUNT(DISTINCT s.source_domain) as active_sources
        FROM mongodb.news_rt.rt_trends t
        CROSS JOIN mongodb.news_rt.rt_sentiment_by_source s
        WHERE t.bucket_date = DATE '{today}'
          AND t.window_start_epoch >= {cutoff_epoch}
          AND s.bucket_date = DATE '{today}'
          AND s.window_start_epoch >= {cutoff_epoch}
        """
        
        df = self.execute_query(query)
        return df.iloc[0].to_dict()
    
    def compare_sentiment_realtime_vs_historical(self, source_domain: str = None) -> pd.DataFrame:
        """
        Compare real-time sentiment with historical averages
        
        Args:
            source_domain: Optional filter by source domain
            
        Returns:
            DataFrame with sentiment comparison
        """
        cutoff_epoch = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        source_filter = f"AND r.source_domain = '{source_domain}'" if source_domain else ""
        
        query = f"""
        WITH realtime_sentiment AS (
          SELECT
            source_domain,
            avg_sentiment as rt_avg_sentiment,
            article_count as rt_article_count
          FROM mongodb.news_rt.rt_sentiment_by_source
          WHERE bucket_date = DATE '{today}'
            AND window_start_epoch >= {cutoff_epoch}
            {source_filter}
        ),
        historical_avg AS (
          SELECT
            source_domain,
            AVG(sentiment.polarity) as hist_avg_sentiment,
            COUNT(*) as hist_article_count
          FROM hive.news_batch.articles_enriched_parquet
          WHERE dt >= '{week_ago}'
            {f"AND source_domain = '{source_domain}'" if source_domain else ""}
          GROUP BY source_domain
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
        ORDER BY ABS(sentiment_delta) DESC
        """
        
        return self.execute_query(query)
    
    def close(self):
        """Close the Presto connection"""
        if self.connection:
            self.connection.close()


def main():
    """Example usage of PrestoNewsClient"""
    
    # Initialize client
    client = PrestoNewsClient(host='localhost', port=8080)
    
    try:
        # Get dashboard metrics
        print("=== Dashboard Metrics ===")
        metrics = client.get_dashboard_metrics()
        for key, value in metrics.items():
            print(f"{key}: {value}")
        
        print("\n=== Trending Topics (Last Hour) ===")
        trends = client.get_trending_topics(hours=1, limit=10)
        print(trends[['topic_token', 'article_count', 'avg_sentiment', 'source_domain']].head())
        
        print("\n=== Sentiment by Source ===")
        sentiment = client.get_sentiment_by_source(hours=1)
        print(sentiment.head())
        
        print("\n=== Sentiment Comparison: Reuters ===")
        comparison = client.compare_sentiment_realtime_vs_historical('reuters.com')
        print(comparison.head())
        
    finally:
        client.close()


if __name__ == '__main__':
    main()

