import sys
import os

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, to_timestamp, to_date, udf, rank, desc
from pyspark.sql.types import StructType, StructField, StringType, LongType, ArrayType, IntegerType, MapType
from pyspark.sql.window import Window

# Khởi tạo Spark
spark = SparkSession.builder \
    .appName("News_Batch_Layer_Modular") \
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY") \
    .master("local[*]") \
    .getOrCreate()

# === [QUAN TRỌNG] GỬI CÁC MODULE CHO WORKER ===
current_dir = os.path.dirname(os.path.abspath(__file__))

# File 1: AI Model
nlp_path = os.path.join(current_dir, "nlp_processor.py")
spark.sparkContext.addPyFile(nlp_path)

# File 2: Topic Modeler (File mới)
topic_path = os.path.join(current_dir, "topic_modeler.py")
spark.sparkContext.addPyFile(topic_path)

print(f">>> Đã gửi modules đến Workers: {nlp_path}, {topic_path}")

# Import các class từ file vệ tinh
from nlp_processor import NewsAnalyzer
from topic_modeler import TopicModeler  # <--- Import class mới
# ==============================================

# --- ĐỊNH NGHĨA SCHEMA ---
image_schema = StructType([
    StructField("url", StringType(), True),
    StructField("caption", StringType(), True)
])

schema = StructType([
    StructField("article_id", StringType(), True),
    StructField("source_domain", StringType(), True),
    StructField("source_feed", StringType(), True),
    StructField("canonical_url", StringType(), True),
    StructField("published_at", LongType(), True),
    StructField("updated_at", LongType(), True),
    StructField("authors", ArrayType(StringType()), True),
    StructField("section", StringType(), True),
    StructField("category", StringType(), True),
    StructField("tags", ArrayType(StringType()), True),
    StructField("title", StringType(), True),
    StructField("body_text", StringType(), True),
    StructField("language", StringType(), True),
    StructField("country", StringType(), True),
    StructField("images", ArrayType(image_schema), True),
    StructField("outlinks", ArrayType(StringType()), True),
    StructField("ingest_time", LongType(), True),
    StructField("crawl_status", StringType(), True),
    StructField("http_status", IntegerType(), True),
    StructField("content_type", StringType(), True),
    StructField("content_length", IntegerType(), True),
    StructField("normalized_title", StringType(), True)
])

# --- 1. EXTRACT ---
input_path = "data/raw_news.json"
if not os.path.exists(input_path):
    input_path = "../data/raw_news.json"

print(f">>> Đang đọc dữ liệu Raw từ: {input_path}")
raw_df = spark.read.option("multiline", "true").schema(schema).json(input_path)

# --- 2. TRANSFORM CƠ BẢN ---
# Chuẩn hóa thời gian & Khử trùng lặp
processed_df = raw_df.withColumn("published_datetime", to_timestamp(col("published_at") / 1000)) \
                     .withColumn("dt", to_date(col("published_datetime")))

windowSpec = Window.partitionBy("article_id").orderBy(desc("updated_at"))
dedup_df = processed_df.withColumn("rank", rank().over(windowSpec)) \
                       .filter(col("rank") == 1) \
                       .drop("rank")

# --- 3. ADVANCED ANALYTICS (GỌI CÁC MODULE CON) ---

# A. Chạy Topic Modeling (Gọi class TopicModeler)
# Code gọn hơn hẳn: Chỉ cần khởi tạo và gọi .run()
tm = TopicModeler(num_topics=6)
topic_df = tm.run(dedup_df)

# B. Chạy AI Sentiment (Gọi class NewsAnalyzer)
print(">>> Đang chạy AI Sentiment Analysis...")
analyzer = NewsAnalyzer()

def apply_sentiment(text):
    return analyzer.analyze_sentiment(text)

def apply_keywords(text):
    return analyzer.extract_keywords(text)

sentiment_udf = udf(apply_sentiment, MapType(StringType(), StringType()))
keyword_udf = udf(apply_keywords, ArrayType(StringType()))

enriched_df = topic_df.withColumn("sentiment_analysis", sentiment_udf(col("body_text"))) \
                      .withColumn("extracted_keywords", keyword_udf(col("body_text")))

# --- 4. LOAD ---
final_output = enriched_df.select(
    "article_id", "source_domain", "published_datetime", "dt",
    "title", "section", "language", "country",
    "topic_id", # Cột từ TopicModeler
    "sentiment_analysis", "extracted_keywords" # Cột từ NewsAnalyzer
)

output_path = "data/simulated_hdfs/articles_enriched"
if input_path.startswith(".."):
    output_path = "../data/simulated_hdfs/articles_enriched"

print(f">>> Đang lưu kết quả xuống Parquet tại: {output_path}")
final_output.write \
    .mode("overwrite") \
    .partitionBy("dt", "source_domain") \
    .parquet(output_path)

print("Job Done.")
spark.stop()