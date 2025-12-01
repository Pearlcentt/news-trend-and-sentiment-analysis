from pyspark.sql.functions import udf, col
from pyspark.sql.types import IntegerType
from pyspark.ml.feature import Tokenizer, StopWordsRemover, CountVectorizer
from pyspark.ml.clustering import LDA
from pyspark.ml import Pipeline

class TopicModeler:
    def __init__(self, num_topics=8, vocab_size=1000):
        self.num_topics = num_topics
        self.vocab_size = vocab_size
        print(f">>> [INIT] TopicModeler đã sẵn sàng (Topics={num_topics})")

    def run(self, df):
        """
        Input: Spark DataFrame (có cột body_text)
        Output: Spark DataFrame (có thêm cột topic_id)
        """
        print(">>> [MLlib] Đang xử lý Text và Training LDA Model...")
        
        # 1. Xử lý null: MLlib ghét null, phải fill bằng chuỗi rỗng
        clean_df = df.na.fill({"body_text": ""})

        # 2. Định nghĩa các giai đoạn (Stages) của Pipeline
        # B1: Tách từ
        tokenizer = Tokenizer(inputCol="body_text", outputCol="words")
        
        # B2: Lọc từ rác (Stopwords)
        remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
        
        # B3: Biến đổi thành Vector số (Features)
        cv = CountVectorizer(inputCol="filtered_words", outputCol="features", 
                             vocabSize=self.vocab_size, minDF=2.0)
        
        # B4: Mô hình LDA (Gom nhóm chủ đề)
        lda = LDA(k=self.num_topics, maxIter=10, featuresCol="features")

        # 3. Tạo và chạy Pipeline
        pipeline = Pipeline(stages=[tokenizer, remover, cv, lda])
        model = pipeline.fit(clean_df)
        transformed_df = model.transform(clean_df)

        # 4. Xử lý kết quả: LDA trả về 'topicDistribution' (Vector xác suất)
        # Ta cần hàm UDF để chọn ra topic có xác suất cao nhất (Argmax)
        
        def get_max_topic(topic_distribution):
            # topic_distribution là Vector [0.1, 0.8, 0.1] -> Trả về index 1
            try:
                return int(topic_distribution.argmax())
            except:
                return -1

        argmax_udf = udf(get_max_topic, IntegerType())

        # 5. Chọn cột cần thiết và dọn dẹp
        result_df = transformed_df.withColumn("topic_id", argmax_udf(col("topicDistribution")))
        
        # Xóa các cột trung gian cho nhẹ DataFrame
        final_df = result_df.drop("words", "filtered_words", "features", "topicDistribution")
        
        print(">>> [MLlib] Đã gán Topic ID thành công.")
        return final_df