"""
Spark batch pipeline (accuracy layer).

Reads historical news_raw data from Kafka, applies heavier NLP,
deduplicates, and writes Parquet partitions to HDFS/S3.

Supports multiple environments via --mode flag:
- docker: Pre-installed JARs, simplified config
- k8s: Full Kubernetes deployment with env vars
- local: Local development with config file
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict
import hashlib

import pyspark.sql.functions as F
from pyspark.sql import SparkSession
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.types import StringType
import yaml


# =============================================================================
# Environment-Aware Configuration
# =============================================================================

def get_env_config(mode: str) -> Dict[str, Any]:
    """Get configuration based on environment mode."""
    if mode == "docker":
        return {
            "kafka": {
                "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
                "topic": "news_raw",
            },
            "spark": {
                "shuffle_partitions": 4,
                "log_level": "WARN",
                "packages": [],  # Pre-installed in Docker image
            },
            "schemas": {
                "news_raw": os.getenv("SCHEMA_PATH", "/opt/spark/work/schemas/news_raw.avsc"),
            },
            "outputs": {
                "parquet_path": "/tmp/output/articles_batch",
            },
        }
    elif mode == "k8s":
        return {
            "kafka": {
                "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka-broker:9092"),
                "topic": os.getenv("KAFKA_TOPIC", "news_raw"),
            },
            "spark": {
                "shuffle_partitions": int(os.getenv("SPARK_SHUFFLE_PARTITIONS", "200")),
                "log_level": os.getenv("SPARK_LOG_LEVEL", "INFO"),
                "packages": [
                    "org.apache.spark:spark-avro_2.12:3.5.3",
                    "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3",
                ],
            },
            "schemas": {
                "news_raw": os.getenv("SCHEMA_PATH", "/app/schemas/news_raw.avsc"),
            },
            "outputs": {
                "parquet_path": os.getenv("OUTPUT_PATH", "hdfs:///data/news/batch"),
            },
        }
    else:  # local - use config file
        return None


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spark batch enrichment job")
    parser.add_argument("--config", default="config/batch-config-local.yaml")
    parser.add_argument("--mode", choices=["docker", "k8s", "local"], default="local",
                        help="Environment mode: docker (pre-installed JARs), k8s (env vars), local (config file)")
    parser.add_argument("--start-ts", help="ISO timestamp lower bound (optional)", required=False)
    parser.add_argument("--end-ts", help="ISO timestamp upper bound (optional)", required=False)
    return parser.parse_args()


def create_spark_session(config: Dict[str, Any], mode: str) -> SparkSession:
    """Create Spark session based on environment mode."""
    builder = SparkSession.builder.appName("NewsBatchLayer")
    
    # Only add packages if not in Docker (Docker has pre-installed JARs)
    packages = config["spark"].get("packages", [])
    if packages:
        builder = builder.config("spark.jars.packages", ",".join(packages))
    
    builder = (
        builder
        .config("spark.sql.shuffle.partitions", config["spark"].get("shuffle_partitions", 200))
        .config("spark.driver.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
        .config("spark.executor.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
    )
    
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel(config["spark"].get("log_level", "INFO"))
    return spark


def heavy_keyword_enrichment(text: str) -> Dict[str, Any]:
    """Placeholder for heavy NLP (topic modeling, embeddings, etc.)."""
    normalized = (text or "").encode("utf-8")
    vector_hash = hashlib.md5(normalized).hexdigest()
    path = f"hdfs:///data/news/vec/{vector_hash[:2]}/{vector_hash}.vec"
    return {"embedding_vector_path": path, "model_version": "nlp-en-v3.2"}


def main():
    args = parse_args()
    
    # Get configuration based on mode
    if args.mode in ("docker", "k8s"):
        config = get_env_config(args.mode)
        print(f"Using {args.mode} mode configuration")
    else:
        config = load_yaml(Path(args.config))
        # Ensure config has expected structure for local mode
        if "inputs" not in config:
            config["inputs"] = {"kafka": config.get("kafka", {})}
    
    # Create Spark session using environment-aware builder
    spark = create_spark_session(config, args.mode)

    schema_json = Path(config["schemas"]["news_raw"]).read_text(encoding="utf-8")

    kafka_cfg = config.get("inputs", {}).get("kafka", config.get("kafka", {}))
    raw_df = (
        spark.read.format("kafka")
        .option("kafka.bootstrap.servers", kafka_cfg["bootstrap_servers"])
        .option("subscribe", kafka_cfg.get("topic", "news_raw"))
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
    print(f"✅ Wrote batch data to Parquet: {config['outputs']['parquet_path']}")

    # 2. Write to MongoDB (Serving Layer)
    # Check if mongo config is present in SparkConf (passed via --conf in Airflow)
    try:
        mongo_output_uri = spark.conf.get("spark.mongodb.output.uri", None)
    except:
        mongo_output_uri = None

    if mongo_output_uri:
        print(f"Writing matching batch data to MongoDB...")
        (
            enriched.select(*output_cols)
            .write.mode("append")
            .format("mongodb")
            .option("uri", mongo_output_uri)
            .save()
        )
        print(f"✅ Wrote batch data to MongoDB: {mongo_output_uri}")
    else:
        print("⚠️ No MongoDB output URI configured. Skipping Mongo write.")


if __name__ == "__main__":
    main()
