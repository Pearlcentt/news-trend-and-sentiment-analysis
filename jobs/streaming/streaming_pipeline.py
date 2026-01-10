"""
Simplified Spark Structured Streaming job for the speed layer.
Consumes from Kafka (news_raw), writes directly to MongoDB.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.types import (
    ArrayType, DoubleType, StringType, StructField, StructType
)
from pymongo import MongoClient
import yaml

# ============= Sentiment Analysis =============
POSITIVE_WORDS = {
    'surge', 'gain', 'rise', 'growth', 'profit', 'success', 'positive',
    'strong', 'bullish', 'optimistic', 'boost', 'rally', 'improve',
    'excellent', 'good', 'great', 'amazing', 'wonderful', 'best'
}
NEGATIVE_WORDS = {
    'drop', 'fall', 'decline', 'loss', 'crash', 'crisis', 'negative',
    'weak', 'bearish', 'pessimistic', 'concern', 'fail', 'worst',
    'terrible', 'bad', 'poor', 'awful', 'horrible', 'disappointing'
}

def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Simple keyword-based sentiment analysis."""
    if not text:
        return {"label": "neu", "polarity": 0.0}
    words = set(text.lower().split())
    pos_count = len(words & POSITIVE_WORDS)
    neg_count = len(words & NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return {"label": "neu", "polarity": 0.0}
    polarity = (pos_count - neg_count) / total
    if polarity > 0.1:
        return {"label": "pos", "polarity": polarity}
    elif polarity < -0.1:
        return {"label": "neg", "polarity": polarity}
    return {"label": "neu", "polarity": polarity}

def extract_keywords(text: str) -> List[Dict[str, Any]]:
    """Extract top keywords by frequency."""
    if not text:
        return []
    stopwords = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have'}
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", text)]
    filtered = [t for t in tokens if t not in stopwords]
    counts = Counter(filtered)
    total = sum(counts.values()) or 1
    return [{"term": term, "score": round(freq/total, 4)} for term, freq in counts.most_common(5)]


def load_yaml(path: Path) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> str:
    return path.read_text()


class MongoWriter:
    def __init__(self, uri: str, database: str):
        self.client = MongoClient(uri)
        self.db = self.client[database]

    def upsert(self, collection: str, records: list, key_fields: list):
        if not records:
            return
        coll = self.db[collection]
        from pymongo import UpdateOne
        ops = [
            UpdateOne(
                {k: r[k] for k in key_fields},
                {"$set": r},
                upsert=True
            ) for r in records
        ]
        if ops:
            coll.bulk_write(ops, ordered=False)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="/tmp/jobs/rt-config.yaml")
    parser.add_argument("--mode", choices=["docker", "k8s", "local"], default="k8s")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_yaml(Path(args.config))
    
    spark = (
        SparkSession.builder.appName("NewsStreamingSimple")
        .config("spark.jars.packages", 
                "org.apache.spark:spark-avro_2.12:3.5.0,"
                "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0")
        .config("spark.sql.shuffle.partitions", 4)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Register UDFs
    sentiment_schema = StructType([
        StructField("label", StringType(), False),
        StructField("polarity", DoubleType(), False)
    ])
    keyword_schema = ArrayType(StructType([
        StructField("term", StringType(), False),
        StructField("score", DoubleType(), False)
    ]))
    
    sentiment_udf = F.udf(analyze_sentiment, sentiment_schema)
    keywords_udf = F.udf(extract_keywords, keyword_schema)

    # Load Avro schema
    news_raw_schema = load_json(Path(config["schemas"]["news_raw"]))
    
    kafka_options = config["kafka"]

    # Read from Kafka
    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_options["bootstrap_servers"])
        .option("subscribe", kafka_options["input_topic"])
        .option("startingOffsets", kafka_options.get("starting_offsets", "latest"))
        .option("failOnDataLoss", "false")
        .load()
    )

    # Parse Avro (strip 5-byte Schema Registry header)
    parsed = raw_stream.select(
        F.col("key").cast("string").alias("article_key"),
        from_avro(F.expr("substring(value, 6)"), news_raw_schema).alias("payload"),
    )

    # Categorization UDF
    def categorize_article(text: str) -> str:
        if not text:
            return "General"
        text = text.lower()
        if any(w in text for w in ['tech', 'software', 'app', 'google', 'apple', 'microsoft', 'ai', 'cyber']):
            return "Technology"
        if any(w in text for w in ['politics', 'government', 'biden', 'trump', 'election', 'congress', 'senate']):
            return "Politics"
        if any(w in text for w in ['sport', 'game', 'player', 'team', 'match', 'league', 'cup', 'olympic']):
            return "Sports"
        if any(w in text for w in ['business', 'market', 'stock', 'economy', 'inflation', 'trade', 'ceo']):
            return "Business"
        if any(w in text for w in ['movie', 'film', 'music', 'song', 'star', 'celebrity', 'hollywood']):
            return "Entertainment"
        if any(w in text for w in ['science', 'space', 'nasa', 'study', 'research', 'climate']):
            return "Science"
        if any(w in text for w in ['war', 'conflict', 'ukraine', 'russia', 'china', 'israel', 'gaza']):
            return "World"
        return "General"

    category_udf = F.udf(categorize_article, StringType())

    enriched = (
        parsed.selectExpr("payload.*")
        # event_time is already a timestamp from Avro logicalType
        .withColumn("event_ts", F.col("event_time"))
        .withColumn("clean_text", F.coalesce(F.col("body_text"), F.lit("")))
        .withColumn("sentiment", sentiment_udf(F.col("clean_text")))
        .withColumn("keywords", keywords_udf(F.col("clean_text")))
        .withColumn("category", category_udf(F.col("clean_text")))
        .withColumn("process_time", F.current_timestamp())
    )

    # MongoDB writer
    mongo_writer = MongoWriter(config["mongo"]["uri"], config["mongo"]["database"])

    def write_batch(batch_df: DataFrame, batch_id: int):
        if batch_df.count() == 0:
            print(f"Batch {batch_id}: No records")
            return
        
        records = []
        for row in batch_df.collect():
            records.append({
                "article_id": row.article_id,
                "source_domain": row.source_domain,
                "title": row.title,
                "body_text": row.body_text[:500] if row.body_text else "",
                "event_time": row.event_time,
                "category": row.category,
                "sentiment": row.sentiment.asDict() if row.sentiment else {"label": "neu", "polarity": 0.0},
                "keywords": [kw.asDict() for kw in row.keywords] if row.keywords else [],
                "processed_at": str(row.process_time),
            })
        
        mongo_writer.upsert("processed_news", records, ["article_id"])
        print(f"Batch {batch_id}: Wrote {len(records)} records to MongoDB")

    # Start streaming query
    query = (
        enriched.writeStream
        .foreachBatch(write_batch)
        .option("checkpointLocation", config["streaming"]["checkpoint_rt_trends"])
        .outputMode("append")
        .start()
    )

    print("Streaming started, waiting for data...")
    query.awaitTermination()


if __name__ == "__main__":
    main()
