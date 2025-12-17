"""
Spark Structured Streaming job for the speed layer.

Consumes Avro records from Kafka (news_raw), applies lightweight NLP,
deduplicates, writes enriched events back to Kafka (news_processed),
and maintains real-time aggregates in MongoDB collections.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from pyspark import StorageLevel
import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.avro.functions import from_avro, to_avro
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pymongo import MongoClient, UpdateOne
import yaml


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "about",
    "into",
    "after",
    "their",
    "they",
    "been",
    "was",
    "were",
    "said",
    "over",
    "upon",
}


def load_json(path: Path) -> str:
    return path.read_text(encoding="utf-8")

# Import enhanced sentiment from spark_utils for consistency
import sys
from pathlib import Path
# Add jobs directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from utils.spark_utils import simple_sentiment, extract_keywords as _extract_kw, extract_entities as _extract_ent
except ImportError:
    # Fallback if import fails - use enhanced local version
    def simple_sentiment(text: str) -> Dict[str, Any]:
        """Enhanced sentiment using VADER-inspired lexicon (fallback)."""
        if not text:
            return {"label": "neu", "polarity": 0.0}
        
        # Comprehensive lexicon (subset for fallback)
        POSITIVE = {
            'excellent': 3.0, 'amazing': 2.8, 'great': 2.2, 'good': 1.5,
            'positive': 1.5, 'growth': 1.5, 'gain': 1.4, 'rise': 1.3,
            'surge': 2.0, 'improve': 1.4, 'success': 2.0, 'strong': 1.4,
            'upbeat': 1.3, 'bullish': 1.4, 'recovery': 1.3, 'profit': 1.3,
        }
        NEGATIVE = {
            'terrible': -2.8, 'awful': -2.7, 'crisis': -2.3, 'crash': -2.3,
            'bad': -1.5, 'negative': -1.4, 'decline': -1.4, 'fall': -1.3,
            'drop': -1.3, 'loss': -1.4, 'weak': -1.3, 'downbeat': -1.3,
            'fail': -2.0, 'recession': -2.2, 'bearish': -1.4, 'plunge': -2.2,
        }
        
        tokens = re.findall(r"[A-Za-z']+", text.lower())
        total_score = 0.0
        count = 0
        
        for token in tokens:
            if token in POSITIVE:
                total_score += POSITIVE[token]
                count += 1
            elif token in NEGATIVE:
                total_score += NEGATIVE[token]
                count += 1
        
        polarity = total_score / (count + 2) if count > 0 else 0.0
        polarity = max(min(polarity, 1.0), -1.0)
        label = "pos" if polarity > 0.1 else "neg" if polarity < -0.1 else "neu"
        return {"label": label, "polarity": round(polarity, 4)}


def extract_keywords(text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Extract top-k keywords by frequency."""
    if not text:
        return []
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", text)]
    filtered = [t for t in tokens if t not in STOPWORDS]
    counts = Counter(filtered)
    total = sum(counts.values()) or 1
    keywords = counts.most_common(top_k)
    return [{"term": term, "score": round(freq / total, 4)} for term, freq in keywords]


def extract_entities(text: str) -> List[Dict[str, str]]:
    """Extract named entities using capitalization patterns."""
    if not text:
        return []
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    unique = list(dict.fromkeys(matches))
    return [{"type": "ORG", "text": entity, "norm": entity.lower().replace(" ", "_")} for entity in unique[:10]]


def derive_topics(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Derive topic IDs from keywords using deterministic hash."""
    import hashlib
    
    topics = []
    for keyword in keywords:
        # Use MD5 for deterministic cross-session hash (PEP 456 safe)
        term_hash = hashlib.md5(keyword["term"].encode()).hexdigest()
        topic_id = int(term_hash[:8], 16) % 1000  # Deterministic 0-999
        topics.append({"topic_id": topic_id, "score": keyword["score"]})
    return topics


def build_udfs():
    sentiment_schema = StructType(
        [StructField("label", StringType()), StructField("polarity", DoubleType())]
    )
    keyword_schema = ArrayType(
        StructType(
            [
                StructField("term", StringType()),
                StructField("score", DoubleType()),
            ]
        )
    )
    entity_schema = ArrayType(
        StructType(
            [
                StructField("type", StringType()),
                StructField("text", StringType()),
                StructField("norm", StringType()),
            ]
        )
    )
    topic_schema = ArrayType(
        StructType(
            [
                StructField("topic_id", IntegerType()),
                StructField("score", DoubleType()),
            ]
        )
    )
    return {
        "sentiment": F.udf(simple_sentiment, sentiment_schema),
        "keywords": F.udf(extract_keywords, keyword_schema),
        "entities": F.udf(extract_entities, entity_schema),
        "topics": F.udf(derive_topics, topic_schema),
    }


class MongoWriter:
    def __init__(self, uri: str, database: str):
        self.client = MongoClient(uri)
        self.db = self.client[database]

    def upsert(self, collection: str, records: List[Dict[str, Any]], keys: List[str]) -> None:
        if not records:
            return
        ops = []
        for record in records:
            filter_doc = {key: record[key] for key in keys}
            ops.append(
                UpdateOne(filter_doc, {"$set": record, "$currentDate": {"_last_upsert": True}}, upsert=True)
            )
        self.db[collection].bulk_write(ops, ordered=False)

    def incremental_upsert(
        self,
        collection: str,
        records: List[Dict[str, Any]],
        keys: List[str],
        inc_fields: List[str],
        set_fields: List[str] | None = None,
    ) -> None:
        if not records:
            return
        set_fields = set_fields or []
        ops = []
        for record in records:
            filter_doc = {key: record[key] for key in keys}
            update_doc: Dict[str, Any] = {
                "$inc": {field: record[field] for field in inc_fields},
                "$currentDate": {"_last_upsert": True},
            }
            if set_fields:
                update_doc["$set"] = {field: record[field] for field in set_fields}
            ops.append(UpdateOne(filter_doc, update_doc, upsert=True))
        self.db[collection].bulk_write(ops, ordered=False)


class CassandraWriter:
    """Writer for Cassandra hot storage - alternative to MongoDB."""
    
    def __init__(self, hosts: List[str], keyspace: str, port: int = 9042):
        self.hosts = hosts
        self.keyspace = keyspace
        self.port = port
        self.session = None
        self._connect()
    
    def _connect(self):
        """Lazy connection to Cassandra cluster."""
        try:
            from cassandra.cluster import Cluster
            cluster = Cluster(self.hosts, port=self.port)
            self.session = cluster.connect(self.keyspace)
            print(f"Connected to Cassandra keyspace: {self.keyspace}")
        except ImportError:
            print("cassandra-driver not installed. Cassandra writes will be skipped.")
            self.session = None
        except Exception as e:
            print(f"Cassandra connection failed: {e}")
            self.session = None
    
    def write_latest_articles(self, records: List[Dict[str, Any]]) -> None:
        """Write individual articles to latest_articles table."""
        if not self.session or not records:
            return
        try:
            query = """
                INSERT INTO latest_articles 
                (article_id, source_domain, title, sentiment_label, sentiment_polarity, published_at, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            prepared = self.session.prepare(query)
            from datetime import datetime
            
            for record in records:
                self.session.execute(prepared, (
                    record.get('article_id', ''),
                    record.get('source_domain', ''),
                    record.get('title', '')[:500] if record.get('title') else '',
                    record.get('sentiment_label', 'neu'),
                    float(record.get('sentiment_polarity', 0.0)),
                    datetime.fromtimestamp(record.get('published_at', 0) / 1000) if record.get('published_at') else datetime.now(),
                    datetime.now()
                ))
            print(f"Wrote {len(records)} articles to Cassandra latest_articles")
        except Exception as e:
            print(f"Cassandra write_latest_articles error: {e}")
    
    def write_rt_trends(self, records: List[Dict[str, Any]]) -> None:
        """Write windowed topic trends to rt_trends table."""
        if not self.session or not records:
            return
        try:
            query = """
                INSERT INTO rt_trends 
                (topic_token, window_start, article_count, avg_sentiment, unique_sources, top_article_ids)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            prepared = self.session.prepare(query)
            from datetime import datetime
            
            for record in records:
                window_start = datetime.fromtimestamp(record.get('window_start_epoch', 0) / 1000) if record.get('window_start_epoch') else datetime.now()
                self.session.execute(prepared, (
                    record.get('topic_token', ''),
                    window_start,
                    int(record.get('article_count', 0)),
                    float(record.get('avg_sentiment', 0.0)),
                    int(record.get('unique_sources', 0)),
                    record.get('top_article_ids', [])[:10]
                ))
            print(f"Wrote {len(records)} trends to Cassandra rt_trends")
        except Exception as e:
            print(f"Cassandra write_rt_trends error: {e}")
    
    def write_sentiment_by_source(self, records: List[Dict[str, Any]]) -> None:
        """Write source sentiment data to rt_sentiment_by_source table."""
        if not self.session or not records:
            return
        try:
            query = """
                INSERT INTO rt_sentiment_by_source 
                (source_domain, bucket_date, window_start, article_count, avg_sentiment)
                VALUES (?, ?, ?, ?, ?)
            """
            prepared = self.session.prepare(query)
            from datetime import datetime, date
            
            for record in records:
                bucket_date = record.get('bucket_date')
                if isinstance(bucket_date, str):
                    bucket_date = datetime.strptime(bucket_date, '%Y-%m-%d').date()
                elif not isinstance(bucket_date, date):
                    bucket_date = datetime.now().date()
                
                window_start = datetime.fromtimestamp(record.get('window_start_epoch', 0) / 1000) if record.get('window_start_epoch') else datetime.now()
                
                self.session.execute(prepared, (
                    record.get('source_domain', ''),
                    bucket_date,
                    window_start,
                    int(record.get('article_count', 0)),
                    float(record.get('avg_sentiment', 0.0))
                ))
            print(f"Wrote {len(records)} records to Cassandra rt_sentiment_by_source")
        except Exception as e:
            print(f"Cassandra write_sentiment_by_source error: {e}")


def foreach_batch_factory(collection: str, keys: List[str], writer: MongoWriter):
    def _foreach(batch_df: DataFrame, batch_id: int):
        records = [json.loads(row) for row in batch_df.toJSON().collect()]
        writer.upsert(collection, records, keys)

    return _foreach


def topic_totals_foreach(writer: MongoWriter):
    def _foreach(batch_df: DataFrame, batch_id: int):
        aggregated = (
            batch_df.groupBy("topic_token", "region", "tier")
            .agg(
                F.count("*").alias("article_count_delta"),
                F.sum("sentiment_polarity").alias("sentiment_sum_delta"),
                F.max("event_ts").alias("latest_event_ts"),
            )
            .withColumn("latest_event_epoch", (F.col("latest_event_ts").cast("long") * 1000))
            .drop("latest_event_ts")
        )
        records = [json.loads(row) for row in aggregated.toJSON().collect()]
        writer.incremental_upsert(
            "rt_topic_totals",
            records,
            ["topic_token", "region", "tier"],
            ["article_count_delta", "sentiment_sum_delta"],
            set_fields=["latest_event_epoch"],
        )

    return _foreach


def parse_args():
    parser = argparse.ArgumentParser(description="Spark Structured Streaming speed layer")
    parser.add_argument("--config", type=str, default="jobs/config/rt-config.yaml")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_yaml(Path(args.config))
    spark_conf = config.get("spark", {})
    spark = (
        SparkSession.builder.appName("NewsSpeedLayer")
        .config("spark.jars.packages", 
                "org.apache.spark:spark-avro_2.12:3.5.3,"
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3")
        .config("spark.sql.shuffle.partitions", spark_conf.get("shuffle_partitions", 200))
        .config("spark.sql.adaptive.enabled", spark_conf.get("adaptive_enabled", True))
        .config(
            "spark.sql.autoBroadcastJoinThreshold", spark_conf.get("auto_broadcast_join_threshold", 64 * 1024 * 1024)
        )
        .config("spark.driver.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
        .config("spark.executor.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
        
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(spark_conf.get("log_level", "WARN"))

    udf_registry = build_udfs()
    news_raw_schema = load_json(Path(config["schemas"]["news_raw"]))
    news_processed_schema = load_json(Path(config["schemas"]["news_processed"]))

    kafka_options = config["kafka"]
    reference_cfg = config.get("reference_data", {})
    source_schema = StructType(
        [
            StructField("source_domain", StringType(), False),
            StructField("region", StringType(), True),
            StructField("tier", StringType(), True),
            StructField("credibility_score", DoubleType(), True),
            StructField("priority_weight", DoubleType(), True),
        ]
    )
    if reference_cfg.get("source_metadata"):
        source_dim = spark.read.schema(source_schema).json(reference_cfg["source_metadata"]).cache()
    else:
        source_dim = spark.createDataFrame([], source_schema)
    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_options["bootstrap_servers"])
        .option("subscribe", kafka_options["input_topic"])
        .option("startingOffsets", kafka_options.get("starting_offsets", "latest"))
        .option("failOnDataLoss", "false")
        .load()
    )

    # Strip 5-byte Confluent Schema Registry header (1 magic byte + 4 schema ID bytes)
    # before Avro deserialization
    parsed = raw_stream.select(
        F.col("key").cast("string").alias("article_key"),
        F.col("partition").alias("raw_partition"),
        F.col("offset").alias("raw_offset"),
        from_avro(F.expr("substring(value, 6)"), news_raw_schema).alias("payload"),
    )

    enriched_base = (
        parsed.selectExpr("payload.*", "raw_partition", "raw_offset")
        .withColumn("event_ts", (F.col("event_time") / 1000).cast("timestamp"))
        .withColumn("ingest_ts", (F.col("ingest_time") / 1000).cast("timestamp"))
    )
    enriched_base = enriched_base.join(F.broadcast(source_dim), on="source_domain", how="left")
    enriched_base = (
        enriched_base.withColumn("region", F.coalesce(F.col("region"), F.lit("unknown")))
        .withColumn("tier", F.coalesce(F.col("tier"), F.lit("unclassified")))
        .withColumn("credibility_score", F.coalesce(F.col("credibility_score"), F.lit(0.5)))
        .withColumn("priority_weight", F.coalesce(F.col("priority_weight"), F.lit(0.5)))
    )

    watermark = config["streaming"]["watermark"]
    deduped = enriched_base.withWatermark("event_ts", watermark).dropDuplicates(
        ["article_id", "content_hash_md5"]
    )

    processed = (
        deduped.withColumn("clean_text", F.trim(F.regexp_replace("body_text", r"\s+", " ")))
        .withColumn("sentiment", udf_registry["sentiment"](F.col("clean_text")))
        .withColumn("keywords", udf_registry["keywords"](F.col("clean_text")))
        .withColumn("entities", udf_registry["entities"](F.col("clean_text")))
        .withColumn("topics", udf_registry["topics"](F.col("keywords")))
        .withColumn("language_conf", F.lit(0.99))
        .withColumn("toxicity_score", F.lit(0.02))
        .withColumn("dedup_group_id", F.col("content_hash_md5"))
        .withColumn("process_time", F.current_timestamp())
    )
    processed.persist(StorageLevel.MEMORY_AND_DISK)

    value_cols = [
        "article_id",
        "source_domain",
        "published_at",
        "language",
        "sentiment",
        "entities",
        "keywords",
        "topics",
        "toxicity_score",
        "clean_text",
        "language_conf",
        "dedup_group_id",
        "raw_partition",
        "raw_offset",
        "ingest_time",
        "process_time",
    ]

    processed_struct = (
        processed.select(*[F.col(col) for col in value_cols])
        .withColumn("process_time", (F.col("process_time").cast("long") * 1000).cast("long"))
        .withColumn("schema_version", F.lit(config["schemas"].get("processed_schema_version", 1)))
    )

    kafka_ready = processed_struct.select(
        F.col("article_id").alias("key"),
        to_avro(
            F.struct(*[F.col(c) for c in processed_struct.columns]),
            news_processed_schema,
        ).alias("value"),
    ).selectExpr("CAST(key AS STRING) AS key", "value")

    kafka_query = (
        kafka_ready.writeStream.outputMode("append")
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_options["bootstrap_servers"])
        .option("topic", kafka_options["output_topic"])
        .option("checkpointLocation", config["streaming"]["checkpoint_news_processed"])
        .start()
    )

    topic_tokens = processed.select(
        F.col("article_id"),
        F.col("source_domain"),
        F.col("region"),
        F.col("tier"),
        F.col("sentiment.label").alias("sentiment_label"),
        F.col("sentiment.polarity").alias("sentiment_polarity"),
        F.col("event_ts"),
        F.expr("transform(keywords, k -> k.term)").alias("topic_terms"),
    ).withColumn("topic_token", F.explode("topic_terms"))

    windowed = (
        topic_tokens.withWatermark("event_ts", watermark)
        .groupBy(
            F.to_date("event_ts").alias("bucket_date"),
            F.window("event_ts", config["streaming"]["window_duration"], config["streaming"]["window_slide"]).alias(
                "win"
            ),
            F.col("topic_token"),
        )
        .agg(
            F.count("*").alias("article_count"),
            F.approx_count_distinct("source_domain").alias("unique_sources"),
            F.avg("sentiment_polarity").alias("avg_sentiment"),
            (F.sum(F.when(F.col("sentiment_label") == "pos", 1).otherwise(0)).cast("double") / F.count("*")).alias(
                "pos_share"
            ),
            (F.sum(F.when(F.col("sentiment_label") == "neg", 1).otherwise(0)).cast("double") / F.count("*")).alias(
                "neg_share"
            ),
            F.slice(F.collect_list("article_id"), 1, 10).alias("top_article_ids"),
        )
        .withColumn("window_start_epoch", (F.col("win.start").cast("long") * 1000))
        .withColumn("window_end_epoch", (F.col("win.end").cast("long") * 1000))
        .withColumn("watermark_epoch", (F.current_timestamp().cast("long") * 1000))
        .drop("win")
    )

    source_sentiment = (
        processed.select(
            F.to_date("event_ts").alias("bucket_date"),
            F.window("event_ts", config["streaming"]["window_duration"], config["streaming"]["window_slide"]).alias(
                "win"
            ),
            F.col("source_domain"),
            F.col("sentiment.polarity").alias("sentiment_polarity"),
        )
        .groupBy("bucket_date", "source_domain", "win")
        .agg(
            F.count("*").alias("article_count"),
            F.avg("sentiment_polarity").alias("avg_sentiment"),
        )
        .withColumn("window_start_epoch", (F.col("win.start").cast("long") * 1000))
        .withColumn("window_end_epoch", (F.col("win.end").cast("long") * 1000))
        .withColumn("updated_at_epoch", (F.current_timestamp().cast("long") * 1000))
        .drop("win")
    )

    sentiment_pivot = (
        topic_tokens.withWatermark("event_ts", watermark)
        .groupBy(
            F.to_date("event_ts").alias("bucket_date"),
            F.window("event_ts", config["streaming"]["window_duration"]).alias("win"),
            F.col("topic_token"),
        )
        .pivot("sentiment_label", ["pos", "neu", "neg"])
        .agg(F.count("*"))
        .na.fill(0, subset=["pos", "neu", "neg"])
        .withColumn("window_start_epoch", (F.col("win.start").cast("long") * 1000))
        .withColumn("window_end_epoch", (F.col("win.end").cast("long") * 1000))
        .drop("win")
    )


    mongo_writer = MongoWriter(config["mongo"]["uri"], config["mongo"]["database"])
    
    # Initialize Cassandra writer if configured
    cassandra_writer = None
    cassandra_cfg = config.get("cassandra", {})
    if cassandra_cfg.get("enabled", False):
        cassandra_hosts = cassandra_cfg.get("hosts", ["cassandra"])
        cassandra_keyspace = cassandra_cfg.get("keyspace", "news_rt")
        cassandra_port = cassandra_cfg.get("port", 9042)
        cassandra_writer = CassandraWriter(cassandra_hosts, cassandra_keyspace, cassandra_port)
        print(f"Cassandra writer initialized: {cassandra_hosts}")
    
    # Combined batch handler for rt_trends (writes to both MongoDB and Cassandra)
    def rt_trends_batch_handler(batch_df: DataFrame, batch_id: int):
        records = [json.loads(row) for row in batch_df.toJSON().collect()]
        mongo_writer.upsert("rt_trends", records, ["bucket_date", "window_start_epoch", "topic_token"])
        if cassandra_writer:
            cassandra_writer.write_rt_trends(records)
    
    # Combined batch handler for rt_sentiment_by_source
    def rt_sentiment_batch_handler(batch_df: DataFrame, batch_id: int):
        records = [json.loads(row) for row in batch_df.toJSON().collect()]
        mongo_writer.upsert("rt_sentiment_by_source", records, ["bucket_date", "window_start_epoch", "source_domain"])
        if cassandra_writer:
            cassandra_writer.write_sentiment_by_source(records)

    rt_trends_query = (
        windowed.writeStream.outputMode("update")
        .foreachBatch(rt_trends_batch_handler)
        .option("checkpointLocation", config["streaming"]["checkpoint_rt_trends"])
        .start()
    )

    rt_sentiment_query = (
        source_sentiment.writeStream.outputMode("update")
        .foreachBatch(rt_sentiment_batch_handler)
        .option("checkpointLocation", config["streaming"]["checkpoint_rt_sentiment"])
        .start()
    )

    pivot_query = (
        sentiment_pivot.writeStream.outputMode("update")
        .foreachBatch(
            foreach_batch_factory(
                "rt_topic_sentiment_pivot",
                ["bucket_date", "window_start_epoch", "topic_token"],
                mongo_writer,
            )
        )
        .option("checkpointLocation", config["streaming"]["checkpoint_rt_topic_pivot"])
        .start()
    )

    totals_query = (
        topic_tokens.writeStream.outputMode("append")
        .foreachBatch(topic_totals_foreach(mongo_writer))
        .option("checkpointLocation", config["streaming"]["checkpoint_rt_topic_totals"])
        .start()
    )

    for query in [kafka_query, rt_trends_query, rt_sentiment_query, pivot_query, totals_query]:
        query.awaitTermination()


if __name__ == "__main__":
    main()
