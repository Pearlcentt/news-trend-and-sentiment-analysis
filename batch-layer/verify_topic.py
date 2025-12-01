from pyspark.sql import SparkSession
from pyspark.sql.functions import col

# Khởi tạo Spark
spark = SparkSession.builder.master("local[*]").getOrCreate()

# Đọc dữ liệu
path = "data/simulated_hdfs/articles_enriched"
print(f"--- Reading data from {path} ---")

try:
    df = spark.read.parquet(path)
except:
    # Fallback nếu chạy từ thư mục batch-layer
    df = spark.read.parquet("../data/simulated_hdfs/articles_enriched")


print("\n📊 Each articles for each topic:")
df.groupBy("topic_id").count().orderBy("topic_id").show()


# Lặp topics
for topic in range(5):
    print(f"\n--- Articles belongs to topic {topic} ---")
    df.filter(col("topic_id") == topic) \
      .select("title", "source_domain") \
      .show(5, truncate=False) # truncate=False để đọc hết tiêu đề

print("\nDone")