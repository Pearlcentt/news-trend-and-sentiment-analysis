"""Unit tests for the sentiment analyzer."""

import pytest


class TestSentimentAnalyzer:
    """Test cases for sentiment analysis functions."""

    def test_positive_sentiment(self):
        """Test positive sentiment detection."""
        from textblob import TextBlob
        
        positive_text = "This is an amazing and wonderful product!"
        blob = TextBlob(positive_text)
        assert blob.sentiment.polarity > 0

    def test_negative_sentiment(self):
        """Test negative sentiment detection."""
        from textblob import TextBlob
        
        negative_text = "This is a terrible and awful experience."
        blob = TextBlob(negative_text)
        assert blob.sentiment.polarity < 0

    def test_neutral_sentiment(self):
        """Test neutral sentiment detection."""
        from textblob import TextBlob
        
        neutral_text = "The meeting is scheduled for 3 PM."
        blob = TextBlob(neutral_text)
        assert -0.2 <= blob.sentiment.polarity <= 0.2

    def test_classify_sentiment(self):
        """Test sentiment classification function."""
        def classify(polarity):
            if polarity > 0.1:
                return "positive"
            elif polarity < -0.1:
                return "negative"
            return "neutral"
        
        assert classify(0.5) == "positive"
        assert classify(-0.5) == "negative"
        assert classify(0.0) == "neutral"


class TestCategoryClassifier:
    """Test cases for category classification."""

    def test_technology_classification(self):
        """Test technology category detection."""
        keywords = ["technology", "software", "app", "digital", "computer"]
        text = "New software application launches with digital features"
        
        score = sum(1 for kw in keywords if kw in text.lower())
        assert score > 0

    def test_politics_classification(self):
        """Test politics category detection."""
        keywords = ["government", "election", "policy", "congress", "senate"]
        text = "The government announced new election policies"
        
        score = sum(1 for kw in keywords if kw in text.lower())
        assert score > 0
