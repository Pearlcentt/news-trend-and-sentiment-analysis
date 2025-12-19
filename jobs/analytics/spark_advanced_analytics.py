"""
Advanced Spark analytics that satisfy the technical checklist:
- Complex aggregations (window, pivot/unpivot, custom UDAF).
- Multiple transformation stages with broadcast + sort-merge joins.
- Spark MLlib sentiment classifier retraining.
- GraphFrames PageRank for entity influence.
- Time-series analysis with rolling windows.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pyspark.sql.functions as F
import yaml
from graphframes import GraphFrame
from pyspark import StorageLevel
from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.ml.feature import (
    HashingTF,
    IDF,
    StopWordsRemover,
    StringIndexer,
    Tokenizer,
)
from pyspark.sql import SparkSession, Window
from pyspark.sql.types import DoubleType, StringType, StructField, StructType


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Advanced Spark analytics for news trends.")
    parser.add_argument("--config", default="jobs/config/analytics-config.yaml")
    return parser.parse_args()


@F.pandas_udf("double", F.PandasUDFType.GROUPED_AGG)
def burstiness(series: pd.Series) -> float:
    """Custom aggregation to capture volatility."""
    if series.empty:
        return 0.0
    mean = series.mean()
    std = series.std()
    if mean == 0:
        return float(std > 0)
    return float(std / abs(mean))


def build_ml_pipeline(max_iter: int) -> Pipeline:
    tokenizer = Tokenizer(inputCol="clean_text", outputCol="tokens")
    remover = StopWordsRemover(inputCol="tokens", outputCol="filtered_tokens")
    hashing = HashingTF(inputCol="filtered_tokens", outputCol="tf", numFeatures=1 << 18)
    idf = IDF(inputCol="tf", outputCol="tfidf")
    label_indexer = StringIndexer(inputCol="label", outputCol="label_index")
    lr = LogisticRegression(
        featuresCol="tfidf",
        labelCol="label_index",
        maxIter=max_iter,
        family="multinomial",
    )
    return Pipeline(stages=[label_indexer, tokenizer, remover, hashing, idf, lr])


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

    articles = (
        spark.read.parquet(inputs["parquet_path"])
        .filter((F.col("dt") >= inputs["start_dt"]) & (F.col("dt") <= inputs["end_dt"]))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )
    articles.count()  # materialize cache

    source_metadata = spark.read.json(inputs["source_metadata"])

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

    rolling_window = Window.partitionBy("topic_id").orderBy("published_ts").rowsBetween(-10, 0)
    topic_rolling = (
        topic_enriched.withColumn("rolling_avg_sentiment", F.avg("sentiment_polarity").over(rolling_window))
        .withColumn("rolling_std_sentiment", F.stddev_pop("sentiment_polarity").over(rolling_window))
        .withColumn("rolling_count", F.count("*").over(rolling_window))
    )

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

    ml_cfg = config.get("ml", {})
    ml_pipeline = build_ml_pipeline(ml_cfg.get("max_iter", 50))
    ml_dataset = articles.select(
        F.col("clean_text"),
        F.col("language"),
        F.col("sentiment.label").alias("label"),
    ).filter(F.col("clean_text").isNotNull())

    train_df, test_df = ml_dataset.randomSplit([0.8, 0.2], seed=42)
    ml_model = ml_pipeline.fit(train_df)
    predictions = ml_model.transform(test_df)
    evaluator = MulticlassClassificationEvaluator(labelCol="label_index", predictionCol="prediction", metricName="f1")
    f1_score = evaluator.evaluate(predictions)
    metrics_df = spark.createDataFrame(
        [(float(f1_score), float(train_df.count()), float(test_df.count()))],
        schema=StructType(
            [
                StructField("f1_score", DoubleType(), False),
                StructField("train_count", DoubleType(), False),
                StructField("test_count", DoubleType(), False),
            ]
        ),
    )
    metrics_df.write.mode("overwrite").json(outputs["ml_metrics_path"])

    spark.sparkContext.setCheckpointDir(config["graphframes"]["checkpoint"])
    entity_edges = (
        articles.select("source_domain", F.explode("entities").alias("entity"))
        .select(F.col("source_domain").alias("src"), F.col("entity.norm").alias("dst"))
        .dropna()
    )

    vertices_sources = articles.select("source_domain").distinct().withColumnRenamed("source_domain", "id")
    vertices_entities = (
        entity_edges.select("dst").withColumnRenamed("dst", "id").distinct()
    )
    vertices = vertices_sources.unionByName(vertices_entities).distinct()
    edges = entity_edges.groupBy("src", "dst").agg(F.count("*").alias("weight"))

    graph = GraphFrame(vertices, edges)
    pagerank = graph.pageRank(resetProbability=0.15, maxIter=10)

    pagerank.vertices.write.mode("overwrite").parquet(outputs["pagerank_path"])

    time_window = Window.partitionBy("language").orderBy("published_ts").rowsBetween(-24, 0)
    time_series_stats = (
        topic_enriched.withColumn("moving_avg_sentiment", F.avg("sentiment_polarity").over(time_window))
        .withColumn("moving_std_sentiment", F.stddev_pop("sentiment_polarity").over(time_window))
        .withColumn("moving_min_sentiment", F.min("sentiment_polarity").over(time_window))
        .withColumn("moving_max_sentiment", F.max("sentiment_polarity").over(time_window))
    )
    time_series_stats.write.mode("overwrite").parquet(outputs["time_series_path"])

    spark.stop()


if __name__ == "__main__":
    main()
