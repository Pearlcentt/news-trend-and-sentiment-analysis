import sys
import os

# --- 1. KHỞI TẠO SPARK ---
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_unixtime, to_timestamp, to_date, udf, rank, desc
from pyspark.sql.types import StructType, StructField, StringType, LongType, ArrayType, IntegerType, MapType
from pyspark.sql.window import Window

# Khởi tạo Spark
spark = SparkSession.builder \
    .appName("News_Batch_Layer_RealAI") \
    .config("spark.sql.legacy.timeParserPolicy", "LEGACY") \
    .master("local[*]") \
    .getOrCreate()

# === [FIX LỖI QUAN TRỌNG] ===
# Gửi file nlp_processor.py đến tất cả các Worker để chúng không bị lỗi ModuleNotFoundError
# Lấy đường dẫn tuyệt đối của file nlp_processor.py (nằm cùng thư mục với file này)
current_dir = os.path.dirname(os.path.abspath(__file__))
nlp_lib_path = os.path.join(current_dir, "nlp_processor.py")

print(f">>> Đang gửi thư viện AI đến Spark Workers: {nlp_lib_path}")
spark.sparkContext.addPyFile(nlp_lib_path)
# ============================

# Import class chứa Model thật
# Lưu ý: Import phải đặt SAU khi addPyFile nếu chạy trên Cluster thật, 
# nhưng chạy local thì đặt đây cũng được, miễn là addPyFile chạy trước khi Action diễn ra.
from nlp_processor import NewsAnalyzer

# --- 2. ĐỊNH NGHĨA SCHEMA ---
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

# --- 3. EXTRACT ---
# Đường dẫn input (tính từ thư mục gốc dự án)
input_path = "data/raw_news.json"

# Kiểm tra file input
# Xử lý đường dẫn tương đối cẩn thận hơn
if not os.path.exists(input_path):
    # Thử tìm ở cấp cha nếu đang chạy từ thư mục con (fallback)
    input_path = "../data/raw_news.json"
    if not os.path.exists(input_path):
        print(f"❌ Lỗi: Không tìm thấy file raw_news.json ở {input_path}")
        sys.exit(1)

print(f">>> Đang đọc dữ liệu Raw từ: {input_path}")
raw_df = spark.read \
    .option("multiline", "true") \
    .schema(schema) \
    .json(input_path)
# -------------------------

# --- 4. TRANSFORM ---

# A. Chuẩn hóa thời gian
processed_df = raw_df.withColumn("published_datetime", to_timestamp(col("published_at") / 1000)) \
                     .withColumn("dt", to_date(col("published_datetime")))

# B. Deduplication
windowSpec = Window.partitionBy("article_id").orderBy(desc("updated_at"))
dedup_df = processed_df.withColumn("rank", rank().over(windowSpec)) \
                       .filter(col("rank") == 1) \
                       .drop("rank")

# C. AI ENRICHMENT (Sử dụng Model Thật)
print(">>> Đang khởi tạo Model AI (Sẽ mất vài giây để tải weights)...")

# Khởi tạo model bên ngoài (Driver)
# Lưu ý: Khi chạy local mode, biến này có thể được worker truy cập.
analyzer = NewsAnalyzer()

def apply_sentiment(text):
    # Gọi hàm phân tích của class
    return analyzer.analyze_sentiment(text)

def apply_keywords(text):
    return analyzer.extract_keywords(text)

# Đăng ký UDF
sentiment_udf = udf(apply_sentiment, MapType(StringType(), StringType()))
keyword_udf = udf(apply_keywords, ArrayType(StringType()))

print(">>> Đang chạy AI Inference trên toàn bộ dữ liệu (Có thể hơi lâu)...")

enriched_df = dedup_df.withColumn("sentiment_analysis", sentiment_udf(col("body_text"))) \
                      .withColumn("extracted_keywords", keyword_udf(col("body_text")))

# --- 5. LOAD ---
final_output = enriched_df.select(
    "article_id", "source_domain", "published_datetime", "dt",
    "title", "authors", "section", "language", "country",
    "sentiment_analysis", "extracted_keywords"
)

# Xử lý đường dẫn output tương tự
output_path = "data/simulated_hdfs/articles_enriched"
if input_path.startswith(".."): # Nếu input dùng .., output cũng nên thế
    output_path = "../data/simulated_hdfs/articles_enriched"

print(f">>> Đang lưu kết quả xuống Parquet tại: {output_path}")

final_output.write \
    .mode("overwrite") \
    .partitionBy("dt", "source_domain") \
    .parquet(output_path)

print("✅ JOB THÀNH CÔNG! Đã dùng model DistilBERT phân tích xong.")
spark.stop()