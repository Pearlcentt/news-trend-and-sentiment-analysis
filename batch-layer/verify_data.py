from pyspark.sql import SparkSession
from pyspark.sql.functions import col, desc

# Khởi tạo Spark
spark = SparkSession.builder.appName("Verify_Result").master("local[*]").getOrCreate()

# Đường dẫn file Parquet (chạy từ thư mục gốc)
path = "data/simulated_hdfs/articles_enriched"

print(f"--- ĐANG ĐỌC DỮ LIỆU TỪ: {path} ---")
try:
    df = spark.read.parquet(path)
except Exception as e:
    print(f"Lỗi: Không tìm thấy data. Hãy chắc chắn bạn đang đứng ở thư mục gốc dự án.\n{e}")
    exit(1)

# 1. Thống kê cơ bản
count = df.count()
print(f"📊 Tổng số bài báo đã xử lý: {count}")

# 2. Quan trọng nhất: Xem AI chấm điểm thế nào
print("\n---Prediction result(Top 20 latest) ---")
df.select("dt", "source_domain", "title", "sentiment_analysis.label", "sentiment_analysis.score") \
  .orderBy(desc("published_datetime")) \
  .show(20, truncate=False) # truncate=False để xem hết tiêu đề dài

# 3. Thống kê tỷ lệ Cảm xúc (Xem bao nhiêu bài tiêu cực/tích cực)
print("\n--- 📈 Sentimental analysis ---")
df.select("sentiment_analysis.label").groupBy("label").count().show()

# # 4. Kiểm tra từ khóa
# print("\n--- keyword extracted ---")
# df.select("title", "extracted_keywords").limit(5).show(truncate=False)