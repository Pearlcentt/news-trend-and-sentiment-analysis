"""
Enhanced Spark Batch Pipeline with Advanced Aggregations.

Demonstrates all course-required batch processing features:
- Complex aggregations (cube, rollup, pivot)
- Window functions with ranking
- Bucketing and partitioning strategies
- Performance optimization (AQE, caching)

Based on patterns from IT4931 spark-lab (Bill Chambers book).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import pyspark.sql.functions as F
from pyspark import StorageLevel
from pyspark.sql import SparkSession, Window
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.types import DoubleType, StringType
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML configuration file."""
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Enhanced Spark Batch Pipeline")
    parser.add_argument("--config", default="jobs/config/batch-config.yaml")
    return parser.parse_args()


# =============================================================================
# Custom UDFs for NLP Processing
# =============================================================================

@F.udf(returnType=DoubleType())
def sentiment_score(text: str) -> float:
    """
    Enhanced sentiment scoring UDF with comprehensive lexicon.
    Uses AFINN-inspired word weights for more accurate sentiment.
    """
    if not text:
        return 0.0
    
    # Comprehensive sentiment lexicon (50+ words with weights)
    positive_words = {
        # Strong positive (weight 3)
        'excellent': 3, 'outstanding': 3, 'amazing': 3, 'fantastic': 3, 'brilliant': 3,
        'exceptional': 3, 'superb': 3, 'wonderful': 3, 'incredible': 3, 'remarkable': 3,
        # Medium positive (weight 2)
        'great': 2, 'good': 2, 'positive': 2, 'strong': 2, 'success': 2, 'successful': 2,
        'growth': 2, 'gain': 2, 'improve': 2, 'improvement': 2, 'surge': 2, 'soar': 2,
        'rise': 2, 'rising': 2, 'boost': 2, 'optimistic': 2, 'upbeat': 2, 'bullish': 2,
        # Mild positive (weight 1)
        'better': 1, 'stable': 1, 'steady': 1, 'recover': 1, 'recovery': 1, 'advance': 1,
        'benefit': 1, 'progress': 1, 'profitable': 1, 'healthy': 1, 'promising': 1,
    }
    
    negative_words = {
        # Strong negative (weight -3)
        'terrible': -3, 'awful': -3, 'disaster': -3, 'catastrophe': -3, 'crisis': -3,
        'collapse': -3, 'crash': -3, 'devastating': -3, 'horrible': -3, 'worst': -3,
        # Medium negative (weight -2)
        'bad': -2, 'negative': -2, 'weak': -2, 'decline': -2, 'fall': -2, 'falling': -2,
        'drop': -2, 'loss': -2, 'losses': -2, 'fail': -2, 'failure': -2, 'cut': -2,
        'plunge': -2, 'slump': -2, 'downbeat': -2, 'bearish': -2, 'recession': -2,
        # Mild negative (weight -1)
        'concern': -1, 'concerns': -1, 'worry': -1, 'worried': -1, 'fear': -1, 'risk': -1,
        'uncertain': -1, 'volatility': -1, 'slowdown': -1, 'pressure': -1, 'struggle': -1,
    }
    
    words = text.lower().split()
    total_weight = 0
    sentiment_words = 0
    
    for word in words:
        # Clean punctuation
        clean_word = ''.join(c for c in word if c.isalpha())
        if clean_word in positive_words:
            total_weight += positive_words[clean_word]
            sentiment_words += 1
        elif clean_word in negative_words:
            total_weight += negative_words[clean_word]
            sentiment_words += 1
    
    # Normalize by total words to get score between -1 and 1
    if len(words) == 0:
        return 0.0
    
    # Scale score to [-1, 1] range
    raw_score = total_weight / max(len(words), 1)
    return max(min(raw_score, 1.0), -1.0)


@F.udf(returnType=StringType())
def sentiment_label(score: float) -> str:
    """Derive sentiment label from score."""
    if score is None:
        return "neutral"
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"


def main():
    args = parse_args()
    config = load_yaml(Path(args.config))
    
    # =========================================================================
    # Spark Session - CLUSTER MODE (not local!)
    # =========================================================================
    import os
    spark_master = os.getenv('SPARK_MASTER_URL', 'spark://spark-master:7077')
    
    spark = (
        SparkSession.builder
        .appName("EnhancedBatchPipeline")
        .config("spark.jars.packages", 
                "org.apache.spark:spark-avro_2.12:3.5.3,"
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3")
        # Performance optimizations
        .config("spark.sql.shuffle.partitions", config.get("spark", {}).get("shuffle_partitions", 200))
        .config("spark.sql.adaptive.enabled", True)  # Adaptive Query Execution
        .config("spark.sql.adaptive.coalescePartitions.enabled", True)
        .config("spark.sql.autoBroadcastJoinThreshold", 64 * 1024 * 1024)  # 64MB
        .config("spark.sql.files.maxPartitionBytes", "128MB")
        # REMOVED:  - Use spark-submit --master instead
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    
    print(f"Spark Master: {spark.sparkContext.master}")

    print("=" * 70)
    print("ENHANCED BATCH PIPELINE - Advanced Aggregations Demo")
    print("=" * 70)

    # =========================================================================
    # 1. DATA INGESTION from Kafka
    # =========================================================================
    print("\n[Step 1] Reading from Kafka...")
    
    schema_path = Path(config.get("schemas", {}).get("news_raw", "schemas/news_raw.avsc"))
    if schema_path.exists():
        schema_json = schema_path.read_text(encoding="utf-8")
    else:
        # Fallback for testing
        schema_json = None
        
    kafka_cfg = config.get("inputs", {}).get("kafka", {})
    bootstrap_servers = kafka_cfg.get("bootstrap_servers", "kafka:9092")
    topic = kafka_cfg.get("topic", "news_raw")
    
    raw_df = (
        spark.read
        .format("kafka")
        .option("kafka.bootstrap.servers", bootstrap_servers)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
    )
    
    total_records = raw_df.count()
    print(f"  Read {total_records} records from Kafka topic '{topic}'")

    # Parse Avro (strip 5-byte Confluent header)
    if schema_json:
        parsed = raw_df.select(
            F.col("key").cast("string").alias("article_id"),
            from_avro(F.expr("substring(value, 6)"), schema_json).alias("payload"),
        ).select("payload.*")
    else:
        # Fallback: create sample data for demo
        parsed = spark.createDataFrame([
            ("art1", "reuters.com", "Tech stocks surge amid market growth", "2025-01-15", "en"),
            ("art2", "bbc.com", "Economy shows positive signs of improvement", "2025-01-15", "en"),
            ("art3", "reuters.com", "Oil prices drop as demand weakens", "2025-01-15", "en"),
            ("art4", "wsj.com", "Healthcare sector gains momentum", "2025-01-16", "en"),
            ("art5", "bbc.com", "Markets decline on trade concerns", "2025-01-16", "en"),
        ], ["article_id", "source_domain", "title", "dt", "language"])

    # Add event timestamp and date partition
    articles = (
        parsed
        .withColumn("event_ts", F.coalesce(
            (F.col("event_time").cast("long") / 1000).cast("timestamp"),
            F.current_timestamp()
        ))
        .withColumn("dt", F.coalesce(
            F.col("dt"),
            F.date_format(F.col("event_ts"), "yyyy-MM-dd")
        ))
        .withColumn("sentiment_score", sentiment_score(F.coalesce(F.col("body_text"), F.col("title"))))
        .withColumn("sentiment_label", sentiment_label(F.col("sentiment_score")))
    )
    
    # Cache for reuse
    articles.persist(StorageLevel.MEMORY_AND_DISK)
    print(f"  Parsed and cached {articles.count()} articles")

    # =========================================================================
    # 2. COMPLEX AGGREGATIONS
    # Based on spark-lab/code/Structured_APIs-Chapter_7_Aggregations.py
    # =========================================================================
    print("\n[Step 2] Complex Aggregations...")
    
    # 2a. Basic Aggregation Statistics
    print("\n  2a. Statistical Aggregations:")
    stats = articles.agg(
        F.count("*").alias("total_articles"),
        F.countDistinct("source_domain").alias("unique_sources"),
        F.avg("sentiment_score").alias("avg_sentiment"),
        F.stddev_pop("sentiment_score").alias("stddev_sentiment"),
        F.var_pop("sentiment_score").alias("variance_sentiment"),
        F.skewness("sentiment_score").alias("skewness"),
        F.kurtosis("sentiment_score").alias("kurtosis"),
    )
    stats.show()
    
    # 2b. PIVOT Operation - Sentiment by Source
    print("\n  2b. PIVOT - Sentiment Distribution by Source:")
    sentiment_pivot = (
        articles
        .groupBy("source_domain")
        .pivot("sentiment_label", ["positive", "neutral", "negative"])
        .agg(F.count("*"))
        .na.fill(0)
    )
    sentiment_pivot.show()
    
    # 2c. UNPIVOT Operation (stack)
    print("\n  2c. UNPIVOT - Stack Operation:")
    sentiment_unpivot = sentiment_pivot.select(
        "source_domain",
        F.expr("stack(3, 'positive', positive, 'neutral', neutral, 'negative', negative) as (sentiment, count)")
    )
    sentiment_unpivot.show()
    
    # 2d. ROLLUP - Hierarchical Aggregation
    print("\n  2d. ROLLUP - Hierarchical Daily Summary:")
    rollup_df = (
        articles
        .rollup("dt", "source_domain")
        .agg(
            F.count("*").alias("article_count"),
            F.avg("sentiment_score").alias("avg_sentiment")
        )
        .orderBy("dt", "source_domain")
    )
    rollup_df.show(20)
    
    # 2e. CUBE - Multi-dimensional Analysis
    print("\n  2e. CUBE - Multi-dimensional Analysis:")
    cube_df = (
        articles
        .cube("dt", "source_domain", "language")
        .agg(
            F.count("*").alias("article_count"),
            F.sum(F.when(F.col("sentiment_label") == "positive", 1).otherwise(0)).alias("positive_count"),
            F.sum(F.when(F.col("sentiment_label") == "negative", 1).otherwise(0)).alias("negative_count")
        )
    )
    cube_df.show(20)

    # =========================================================================
    # 3. WINDOW FUNCTIONS WITH RANKING
    # Based on spark-lab/code/Structured_APIs-Chapter_7_Aggregations.py
    # =========================================================================
    print("\n[Step 3] Window Functions with Ranking...")
    
    # 3a. Running totals and rankings
    windowSpec = (
        Window
        .partitionBy("source_domain")
        .orderBy(F.desc("sentiment_score"))
        .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )
    
    ranked = articles.select(
        "article_id",
        "source_domain",
        "title",
        "sentiment_score",
        F.rank().over(windowSpec).alias("rank"),
        F.dense_rank().over(windowSpec).alias("dense_rank"),
        F.row_number().over(windowSpec).alias("row_num"),
        F.max("sentiment_score").over(windowSpec).alias("running_max"),
        F.sum(F.lit(1)).over(windowSpec).alias("running_count"),
    )
    
    print("\n  3a. Ranking within Source Domain:")
    ranked.show(20, truncate=50)
    
    # 3b. Rolling window for time-series analysis
    timeWindow = (
        Window
        .partitionBy("source_domain")
        .orderBy("dt")
        .rowsBetween(-7, 0)  # 7-day rolling window
    )
    
    rolling_stats = articles.groupBy("source_domain", "dt").agg(
        F.count("*").alias("daily_count"),
        F.avg("sentiment_score").alias("daily_sentiment")
    ).select(
        "source_domain",
        "dt",
        "daily_count",
        "daily_sentiment",
        F.avg("daily_sentiment").over(timeWindow).alias("7day_avg_sentiment"),
        F.sum("daily_count").over(timeWindow).alias("7day_total_articles"),
    )
    
    print("\n  3b. 7-Day Rolling Window Statistics:")
    rolling_stats.orderBy("source_domain", "dt").show(20)
    
    # 3c. Lag/Lead for trend comparison
    lagLeadWindow = Window.partitionBy("source_domain").orderBy("dt")
    
    trend_analysis = rolling_stats.select(
        "source_domain",
        "dt",
        "daily_sentiment",
        F.lag("daily_sentiment", 1).over(lagLeadWindow).alias("prev_day_sentiment"),
        F.lead("daily_sentiment", 1).over(lagLeadWindow).alias("next_day_sentiment"),
        (F.col("daily_sentiment") - F.lag("daily_sentiment", 1).over(lagLeadWindow)).alias("sentiment_change")
    )
    
    print("\n  3c. Lag/Lead Trend Analysis:")
    trend_analysis.show(20)

    # =========================================================================
    # 4. BUCKETING AND PARTITIONING
    # =========================================================================
    print("\n[Step 4] Bucketing and Partitioning...")
    
    output_path = config.get("outputs", {}).get("parquet_path", "/tmp/output/articles_enriched")
    
    # 4a. Write with partitioning by date and language
    print(f"\n  4a. Writing partitioned Parquet to {output_path}")
    (
        articles
        .select(
            "article_id", "source_domain", "title", "dt", "language",
            "sentiment_score", "sentiment_label", "event_ts"
        )
        .write
        .mode("overwrite")
        .partitionBy("dt", "language")
        .option("compression", "snappy")
        .parquet(output_path)
    )
    
    # 4b. Write bucketed table (for optimized joins)
    print("\n  4b. Creating bucketed table for optimized joins...")
    spark.sql("CREATE DATABASE IF NOT EXISTS news_analytics")
    
    (
        articles
        .select("article_id", "source_domain", "sentiment_score", "dt")
        .write
        .mode("overwrite")
        .bucketBy(16, "source_domain")
        .sortBy("source_domain", "dt")
        .saveAsTable("news_analytics.articles_bucketed")
    )
    
    # =========================================================================
    # 5. Save Aggregation Results
    # =========================================================================
    print("\n[Step 5] Saving Aggregation Results...")
    
    agg_output = config.get("outputs", {}).get("aggregations_path", "/tmp/output/aggregations")
    
    sentiment_pivot.write.mode("overwrite").parquet(f"{agg_output}/sentiment_pivot")
    rollup_df.write.mode("overwrite").parquet(f"{agg_output}/daily_rollup")
    cube_df.write.mode("overwrite").parquet(f"{agg_output}/multidim_cube")
    rolling_stats.write.mode("overwrite").parquet(f"{agg_output}/rolling_stats")

    # =========================================================================
    # 6. Explain Execution Plan (for debugging)
    # =========================================================================
    print("\n[Step 6] Execution Plan Analysis...")
    print("\n  Sample Explain Plan for Cube Aggregation:")
    cube_df.explain(mode="formatted")
    
    print("\n" + "=" * 70)
    print("BATCH PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 70)
    
    # Cleanup
    articles.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()
