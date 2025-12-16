"""
Spark batch pipeline (accuracy layer).

Reads historical news_raw data from Kafka, applies heavier NLP,
deduplicates, and writes Parquet partitions to HDFS/S3.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict
import hashlib

import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.types import StringType
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spark batch enrichment job")
    parser.add_argument("--config", default="config/batch-config-local.yaml")
    parser.add_argument("--start-ts", help="ISO timestamp lower bound (optional)", required=False)
    parser.add_argument("--end-ts", help="ISO timestamp upper bound (optional)", required=False)
    return parser.parse_args()


def heavy_keyword_enrichment(text: str) -> Dict[str, Any]:
    """Placeholder for heavy NLP (topic modeling, embeddings, etc.)."""
    normalized = (text or "").encode("utf-8")
    vector_hash = hashlib.md5(normalized).hexdigest()
    path = f"hdfs:///data/news/vec/{vector_hash[:2]}/{vector_hash}.vec"
    return {"embedding_vector_path": path, "model_version": "nlp-en-v3.2"}


def main():
    args = parse_args()
    config = load_yaml(Path(args.config))
    spark = (
        SparkSession.builder.appName("NewsBatchLayer")
        .config("spark.jars.packages", 
                "org.apache.spark:spark-avro_2.12:3.5.3,"
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3")
        .config("spark.sql.shuffle.partitions", config["spark"].get("shuffle_partitions", 200))
        .config("spark.driver.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
        .config("spark.executor.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
        
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(config["spark"].get("log_level", "INFO"))

    schema_json = Path(config["schemas"]["news_raw"]).read_text(encoding="utf-8")

    kafka_cfg = config["inputs"]["kafka"]
    raw_df = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", kafka_cfg["bootstrap_servers"])
        .option("subscribe", kafka_cfg["topic"])
        .option("startingOffsets", "earliest")
        .option("endingOffsets", "latest")
        .load()
    )

    # Strip 5-byte Confluent Schema Registry header before Avro deserialization
    parsed = raw_df.select(
        F.col("key").cast("string").alias("article_id"),
        from_avro(F.expr("substring(value, 6)"), schema_json).alias("payload"),
    ).select("payload.*")

    # Handle event_time which comes as timestamp-millis (cast to long first if needed, then to timestamp)
    with_dt = parsed.withColumn(
        "event_ts", 
        F.when(
            F.col("event_time").cast("long").isNotNull(),
            (F.col("event_time").cast("long") / 1000).cast("timestamp")
        ).otherwise(F.current_timestamp())
    ).withColumn(
        "dt", F.date_format(F.col("event_ts"), "yyyy-MM-dd")
    )

    deduped = with_dt.dropDuplicates(["article_id", "content_hash_md5"])

    embeddings_udf = F.udf(
        lambda text: heavy_keyword_enrichment(text)["embedding_vector_path"], StringType()
    )
    model_version_udf = F.udf(
        lambda text: heavy_keyword_enrichment(text)["model_version"], StringType()
    )

    enriched = (
        deduped.withColumn("embedding_vector_path", embeddings_udf(F.col("body_text")))
        .withColumn("model_version", model_version_udf(F.col("body_text")))
        .withColumn("preprocess_version", F.lit("clean-1.5"))
        .withColumn("language", F.col("language"))
    )

    output_cols = [
        "dt",
        "article_id",
        "source_domain",
        "published_at",
        "language",
        "content_hash_md5",
        "sentiment",
        "entities",
        "keywords",
        "topics",
        "embedding_vector_path",
        "model_version",
        "preprocess_version",
    ]

    (
        enriched.select(*output_cols)
        .write.mode("append")
        .partitionBy("dt", "language")
        .format("parquet")
        .save(config["outputs"]["parquet_path"])
    )


if __name__ == "__main__":
    main()
