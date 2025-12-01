from transformers import pipeline

class NewsAnalyzer:
    def __init__(self):
        print(">>> [INIT] Đang tải model AI 'distilbert-base-uncased-finetuned-sst-2-english'...")
        # Load pipeline một lần duy nhất khi khởi tạo class
        # device=-1 nghĩa là chạy CPU (nếu có GPU set device=0)
        self.sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            framework="pt" # Sử dụng PyTorch
        )
        print("Model AI đã tải thành công!")

    def analyze_sentiment(self, text):
        """
        Input: Body text của bài báo.
        Output: Dictionary {'label': 'positive/negative', 'score': '0.99'}
        """
        if not text or len(text.strip()) == 0:
            return {"label": "neutral", "score": "0.0"}

        try:
            # Model BERT chỉ nhận tối đa 512 tokens. 
            # truncation=True: Tự động cắt phần đuôi nếu bài quá dài.
            # max_length=512: Giới hạn độ dài.
            result = self.sentiment_pipeline(text, truncation=True, max_length=512)
            
            # Kết quả trả về dạng list: [{'label': 'POSITIVE', 'score': 0.998}]
            top_result = result[0]
            
            return {
                "label": top_result['label'].lower(), # Chuyển POSITIVE -> positive
                "score": str(round(top_result['score'], 4))
            }
        except Exception as e:
            print(f"Error while reading articles: {e}")
            return {"label": "error", "score": "0.0"}

    def extract_keywords(self, text):
        """
        Model DistilBERT ở trên chỉ làm Sentiment, không trích xuất từ khóa.
        Nên ta vẫn giữ logic Rule-based (từ điển) cho phần này để code không bị thiếu chức năng.
        """
        if not text: return []
        
        keywords = []
        text_lower = text.lower()
        
        # Danh sách từ khóa tài chính quan trọng cần bắt
        vocab = [
            "federal reserve", "ecb", "inflation", "interest rates", "ai", 
            "gdp", "oil", "nasdaq", "s&p 500", "recession", "bankruptcy",
            "central bank", "layoff", "revenue", "profit"
        ]
        
        for word in vocab:
            if word in text_lower:
                keywords.append(word.replace(" ", "_"))
        
        return list(set(keywords))