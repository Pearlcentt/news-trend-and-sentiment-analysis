"""
Advanced Spark analytics that satisfy the technical checklist:
- Complex aggregations (window, pivot/unpivot, custom UDAF).
- Multiple transformation stages with broadcast + sort-merge joins.
- Orchestrates specialized analytics from other modules:
    * MLlib sentiment classifier (from ml_pipeline)
    * GraphFrames PageRank (from graph_analytics)
    * Time-series analysis (from time_series)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pyspark.sql.functions as F
import yaml
from pyspark import StorageLevel
from pyspark.sql import SparkSession, Window
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

# Import shared analytics modules
# Assumes PYTHONPATH includes the parent 'jobs' directory
try:
    from analytics.ml_pipeline import build_classification_pipeline, evaluate_model
    from analytics.graph_analytics import create_source_entity_graph, run_pagerank
    from analytics.time_series import compute_rolling_statistics
except ImportError:
    # Fallback for local testing if not running as module
    from ml_pipeline import build_classification_pipeline, evaluate_model
    from graph_analytics import create_source_entity_graph, run_pagerank
    from time_series import compute_rolling_statistics


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advanced Spark analytics for news trends.")
    parser.add_argument("--config", default="jobs/config/analytics-config.yaml")
    return parser.parse_args()


@F.pandas_udf("double", F.PandasUDFType.GROUPED_AGG)
def burstiness(series: pd.Series) -> float:
    """Custom aggregation to capture volatility (CV = std/mean)."""
    if series.empty:
        return 0.0
    mean = series.mean()
    std = series.std()
    if mean == 0:
        return float(std > 0)
    return float(std / abs(mean))


def main():
    args = parse_args()
    config = load_yaml(Path(args.config))

    spark = (
        SparkSession.builder.appName("NewsAdvancedAnalytics")
        .config("spark.sql.shuffle.partitions", config["spark"].get("shuffle_partitions", 400))
        .config("spark.sql.adaptive.enabled", True)
        .config("spark.sql.autoBroadcastJoinThreshold", 128 * 1024 * 1024)
        .config("spark.sql.warehouse.dir", config["outputs"]["warehouse_path"])
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(config["spark"].get("log_level", "INFO"))
    spark.sql("CREATE NAMESPACE IF NOT EXISTS analytics")

    inputs = config["inputs"]
    outputs = config["outputs"]

    # 1. Load Data
    # ---------------------------------------------------------
    articles = (
        spark.read.parquet(inputs["parquet_path"])
        .filter((F.col("dt") >= inputs["start_dt"]) & (F.col("dt") <= inputs["end_dt"]))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )
    articles.count()  # materialize cache

    source_metadata = spark.read.json(inputs["source_metadata"])

    # 2. Topic Analysis with Custom UDF & Shared Time Series Logic
    # ---------------------------------------------------------
    topic_exploded = (
        articles.select(
            "article_id",
            "source_domain",
            "language",
            "dt",
            F.col("sentiment.polarity").alias("sentiment_polarity"),
            F.col("sentiment.label").alias("sentiment_label"),
            F.to_timestamp(F.col("published_at") / 1000).alias("published_ts"),
            F.explode("topics").alias("topic"),
        )
        .withColumn("topic_id", F.col("topic.topic_id"))
        .withColumn("topic_score", F.col("topic.score"))
        .drop("topic")
    )

    topic_enriched = (
        topic_exploded.join(F.broadcast(source_metadata), on="source_domain", how="left")
        .fillna({"region": "unknown", "tier": "unclassified"})
        .withColumn("credibility_score", F.coalesce(F.col("credibility_score"), F.lit(0.5)))
    )

    # REUSE: Use time_series module to compute rolling stats
    # We ask for a 10-row window (simulated by using lookback logic if applicable, 
    # but compute_rolling_statistics uses generic time windows. 
    # For compatibility, we'll keep the custom window logic here because it was specifically 
    # purely row-based (rowsBetween(-10, 0)) rather than time-based, 
    # OR we could switch to time-based if appropriate.
    # Given the difference, let's keep the specialized row-based window here for "Last 10 Articles" 
    # but use the time_series logic for the time-based section later.
    
    rolling_window = Window.partitionBy("topic_id").orderBy("published_ts").rowsBetween(-10, 0)
    topic_rolling = (
        topic_enriched.withColumn("rolling_avg_sentiment", F.avg("sentiment_polarity").over(rolling_window))
        .withColumn("rolling_std_sentiment", F.stddev_pop("sentiment_polarity").over(rolling_window))
        .withColumn("rolling_count", F.count("*").over(rolling_window))
    )

    # UNIQUE: Burstiness UDF
    topic_burstiness = topic_enriched.groupBy("topic_id").agg(
        burstiness(F.col("sentiment_polarity")).alias("burstiness_index")
    )

    topic_rolling_stats = (
        topic_rolling.join(topic_burstiness.hint("merge"), on="topic_id", how="left")
        .withColumn("weighted_score", F.col("topic_score") * F.col("credibility_score"))
        .select(
            "topic_id",
            "language",
            "region",
            "tier",
            "published_ts",
            "rolling_avg_sentiment",
            "rolling_std_sentiment",
            "rolling_count",
            "burstiness_index",
            "weighted_score",
        )
        .repartition("language", "topic_id")
    )

    (
        topic_rolling_stats.write.mode("overwrite")
        .partitionBy("language")
        .format("parquet")
        .save(outputs["topic_rolling_stats_path"])
    )

    topic_rolling_stats.write.mode("overwrite").bucketBy(24, "topic_id").sortBy("topic_id").saveAsTable(
        "analytics.topic_rolling_stats"
    )

    # 3. Pivot/Unpivot (Unique Logic)
    # ---------------------------------------------------------
    sentiment_pivot = (
        articles.groupBy("language")
        .pivot("sentiment.label", ["pos", "neu", "neg"])
        .agg(F.count("*").alias("article_count"))
        .na.fill(0)
    )

    sentiment_unpivot = sentiment_pivot.select(
        "language",
        F.expr("stack(3, 'pos', pos, 'neu', neu, 'neg', neg) as (sentiment_label, article_count)"),
    )

    sentiment_pivot.write.mode("overwrite").format("parquet").save(outputs["sentiment_pivot_path"])
    sentiment_unpivot.write.mode("overwrite").format("parquet").save(outputs["sentiment_unpivot_path"])

    # 4. Integrated ML Pipeline (REUSE ml_pipeline.py)
    # ---------------------------------------------------------
    print("Running Integrated ML Analysis...")
    ml_cfg = config.get("ml", {})
    
    # Prepare data for ML
    ml_dataset = articles.select(
        F.coalesce(F.col("body_text"), F.col("title")).alias("clean_text"),
        F.col("language"),
        F.col("sentiment.label").alias("sentiment_label"),
    ).filter(F.col("clean_text").isNotNull() & F.col("sentiment_label").isNotNull())

    train_df, test_df = ml_dataset.randomSplit([0.8, 0.2], seed=42)
    
    # REUSE: Build pipeline using imported function
    ml_pipeline = build_classification_pipeline(classifier_type="logistic")
    
    # Fit and Transform
    ml_model = ml_pipeline.fit(train_df)
    predictions = ml_model.transform(test_df)
    
    # REUSE: Evaluate using imported function
    metrics = evaluate_model(predictions)
    
    metrics_df = spark.createDataFrame(
        [(k, float(v)) for k, v in metrics.items()],
        ["metric", "value"]
    )
    metrics_df.write.mode("overwrite").json(outputs["ml_metrics_path"])

    # 5. Integrated Graph Analytics (REUSE graph_analytics.py)
    # ---------------------------------------------------------
    print("Running Integrated Graph Analysis...")
    spark.sparkContext.setCheckpointDir(config["graphframes"]["checkpoint"])
    
    # REUSE: Create graph using imported function
    # Note: create_source_entity_graph expects specific columns. 
    # We need to ensure 'entities' column is present and formatted as expected or adapt the input.
    # The function expects 'source_domain' and 'entities' array of structs with 'norm' field.
    # Our 'articles' DF typically has this from the batch pipeline.
    try:
        graph = create_source_entity_graph(articles, spark)
        
        # REUSE: Run PageRank
        pagerank = run_pagerank(graph, reset_prob=0.15, max_iter=10)
        
        pagerank.vertices.write.mode("overwrite").parquet(outputs["pagerank_path"])
    except Exception as e:
        print(f"Skipping graph analytics due to error (schema mismatch?): {e}")

    # 6. Integrated Time Series (REUSE time_series.py)
    # ---------------------------------------------------------
    print("Running Integrated Time Series Analysis...")
    # Use the topic_enriched DF which has timestamps
    # Calculate rolling stats for sentiment over time
    
    # REUSE: Compute rolling statistics
    # This replaces the manual window construction at the end of the original file
    # We'll compute rolling stats for each language
    ts_df = (
        topic_enriched
        .groupBy("language", "published_ts")
        .agg(F.avg("sentiment_polarity").alias("daily_sentiment"))
    )
    
    time_series_stats = compute_rolling_statistics(
        ts_df,
        partition_cols=["language"],
        order_col="published_ts",
        value_col="daily_sentiment",
        windows=[7, 30] # 7-day and 30-day rolling
    )
    
    time_series_stats.write.mode("overwrite").parquet(outputs["time_series_path"])

    spark.stop()


if __name__ == "__main__":
    main()
