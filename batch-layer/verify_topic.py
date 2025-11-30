from pyspark.sql import SparkSession
from pyspark.sql.functions import col

# Khởi tạo Spark
spark = SparkSession.builder.master("local[*]").getOrCreate()

# Đọc dữ liệu
path = "data/simulated_hdfs/articles_enriched"
print(f"--- ĐANG ĐỌC DATA TỪ: {path} ---")

try:
    df = spark.read.parquet(path)
except:
    # Fallback nếu chạy từ thư mục batch-layer
    df = spark.read.parquet("../data/simulated_hdfs/articles_enriched")

# 1. Xem phân bố (Mỗi topic có bao nhiêu bài?)
print("\n📊 SỐ LƯỢNG BÀI BÁO THEO TỪNG TOPIC:")
df.groupBy("topic_id").count().orderBy("topic_id").show()

# 2. Soi chi tiết từng Topic để xem nó là chủ đề gì
# Lặp qua 3 topic (0, 1, 2)
for topic in [0, 1, 2]:
    print(f"\n--- 🔍 MẪU BÀI VIẾT THUỘC TOPIC {topic} ---")
    df.filter(col("topic_id") == topic) \
      .select("title", "source_domain") \
      .show(5, truncate=False) # truncate=False để đọc hết tiêu đề

print("\n✅ XONG! Dựa vào tiêu đề trên, bạn hãy tự đoán xem Topic 0, 1, 2 là chủ đề gì nhé.")