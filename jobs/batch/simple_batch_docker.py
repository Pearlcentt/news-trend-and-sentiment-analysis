"""
Simple batch job for Docker Spark - uses pre-installed JARs.
"""
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.avro.functions import from_avro
import pyspark.sql.functions as F

print("Starting Docker Spark Batch Job")
print("=" * 60)

# Load schema
schema_path = Path("/opt/spark/work/schemas/news_raw.avsc")
schema_json = schema_path.read_text()
print(f"Schema loaded: {len(schema_json)} chars")

# Create Spark session (no packages needed - JARs pre-installed)
spark = (
    SparkSession.builder
    .appName("DockerBatchJob")
    
    .config("spark.sql.shuffle.partitions", "4")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")
print("Spark session created")

# Read from Kafka
print("Reading from Kafka...")
raw_df = (
    spark.read
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "news_raw")
    .option("startingOffsets", "earliest")
    .option("endingOffsets", "latest")
    .load()
)
count = raw_df.count()
print(f"Read {count} messages from Kafka")

# Parse Avro (strip 5-byte Confluent header)
print("Parsing Avro with Confluent header stripping...")
parsed = raw_df.select(
    F.col("key").cast("string").alias("article_id"),
    from_avro(F.expr("substring(value, 6)"), schema_json).alias("payload"),
).select("payload.*")

print(f"Parsed schema: {parsed.schema.simpleString()[:200]}...")

# Add date partition
print("Adding date partition column...")
with_dt = parsed.withColumn(
    "event_ts",
    F.when(
        F.col("event_time").cast("long").isNotNull(),
        (F.col("event_time").cast("long") / 1000).cast("timestamp")
    ).otherwise(F.current_timestamp())
).withColumn(
    "dt", F.date_format(F.col("event_ts"), "yyyy-MM-dd")
)

# Deduplicate
deduped = with_dt.dropDuplicates(["article_id", "content_hash_md5"])
final_count = deduped.count()
print(f"After dedup: {final_count} records")

# Select output columns (only those that exist)
available_cols = deduped.columns
output_cols = [c for c in ["dt", "article_id", "source_domain", "title", "language", "content_hash_md5", "event_ts"] if c in available_cols]
print(f"Output columns: {output_cols}")

# Write to Parquet
output_path = "/tmp/output/articles_batch"
print(f"Writing to {output_path}...")
(
    deduped.select(*output_cols)
    .write
    .mode("overwrite")
    .partitionBy("dt")
    .format("parquet")
    .save(output_path)
)

# Verify output
print("Verifying output...")
result = spark.read.parquet(output_path)
result.show(5, truncate=50)
print(f"Total rows written: {result.count()}")

spark.stop()
print("=" * 60)
print("Batch job completed successfully!")
