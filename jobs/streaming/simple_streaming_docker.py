"""
Simple streaming job for Docker Spark - uses pre-installed JARs.
Reads from Kafka, parses Avro, writes to MongoDB real-time aggregates.

Supports both Docker Compose and Kubernetes via environment variables:
- KAFKA_BOOTSTRAP_SERVERS: defaults to 'kafka:9092' (Docker) or 'kafka-broker:9092' (K8s)
- MONGODB_HOST: defaults to 'mongo' (Docker) or 'mongodb' (K8s)
"""
import os
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.avro.functions import from_avro
import pyspark.sql.functions as F
from pymongo import MongoClient

# Environment-aware configuration
KAFKA_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
MONGODB_HOST = os.getenv('MONGODB_HOST', 'mongo')
MONGODB_URI = f"mongodb://{MONGODB_HOST}:27017"

print("Starting Docker Spark Streaming Job")
print("=" * 60)
print(f"Kafka: {KAFKA_SERVERS}, MongoDB: {MONGODB_URI}")

# Load schema
schema_path = Path("/opt/spark/work/schemas/news_raw.avsc")
schema_json = schema_path.read_text()
print(f"Schema loaded: {len(schema_json)} chars")

# Create Spark session (no packages needed - JARs pre-installed)
spark = (
    SparkSession.builder
    .appName("DockerStreamingJob")
    
    .config("spark.sql.shuffle.partitions", "4")
    .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
print("Spark session created")

# Read from Kafka as stream
print("Creating Kafka stream...")
raw_stream = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_SERVERS)
    .option("subscribe", "news_raw")
    .option("startingOffsets", "earliest")
    .option("failOnDataLoss", "false")
    .load()
)
print("Kafka stream created")

# Parse Avro (strip 5-byte Confluent header)
parsed = raw_stream.select(
    F.col("key").cast("string").alias("article_id"),
    from_avro(F.expr("substring(value, 6)"), schema_json).alias("payload"),
    F.col("timestamp").alias("kafka_ts")
).select("payload.*", "kafka_ts")

# Add event timestamp
enriched = parsed.withColumn(
    "event_ts",
    F.when(
        F.col("event_time").cast("long").isNotNull(),
        (F.col("event_time").cast("long") / 1000).cast("timestamp")
    ).otherwise(F.current_timestamp())
)

# Define foreachBatch function to write to MongoDB
def write_to_mongo(batch_df, batch_id):
    """Write batch aggregates to MongoDB."""
    if batch_df.isEmpty():
        print(f"Batch {batch_id}: empty, skipping")
        return
    
    count = batch_df.count()
    print(f"Batch {batch_id}: processing {count} records")
    
    # Aggregate by source_domain for real-time trends
    trends = (
        batch_df
        .groupBy("source_domain")
        .agg(F.count("*").alias("article_count"))
        .collect()
    )
    
    # Write to MongoDB
    try:
        client = MongoClient(MONGODB_URI)
        db = client["news_rt"]
        
        # Update rt_trends collection
        for row in trends:
            db.rt_trends.update_one(
                {"source_domain": row["source_domain"]},
                {"$inc": {"article_count": row["article_count"]}},
                upsert=True
            )
        
        # Record batch info
        from datetime import datetime
        db.rt_batches.insert_one({
            "batch_id": batch_id,
            "record_count": count,
            "sources": len(trends),
            "processed_at": datetime.now()  # Use Python datetime, not Spark Column
        })
        
        client.close()
        print(f"Batch {batch_id}: wrote {len(trends)} source aggregates to MongoDB")
    except Exception as e:
        print(f"Batch {batch_id}: MongoDB error: {e}")

# Start streaming query with foreachBatch
print("Starting streaming query...")
query = (
    enriched.writeStream
    .foreachBatch(write_to_mongo)
    .option("checkpointLocation", "/tmp/checkpoints/streaming_job")
    .trigger(processingTime="10 seconds")
    .start()
)

print(f"Streaming query started: {query.id}")
print("Processing will run for 60 seconds...")

# Wait for 60 seconds then stop
query.awaitTermination(60)
query.stop()

# Verify MongoDB results
print("\nVerifying MongoDB results...")
try:
    client = MongoClient(MONGODB_URI)
    db = client["news_rt"]
    
    trends_count = db.rt_trends.count_documents({})
    batch_count = db.rt_batches.count_documents({})
    
    print(f"rt_trends documents: {trends_count}")
    print(f"rt_batches documents: {batch_count}")
    
    print("\nSample rt_trends:")
    for doc in db.rt_trends.find().limit(5):
        print(f"  {doc}")
    
    client.close()
except Exception as e:
    print(f"MongoDB verification error: {e}")

spark.stop()
print("=" * 60)
print("Streaming job completed!")
