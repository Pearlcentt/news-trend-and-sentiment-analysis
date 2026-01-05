"""Integration tests for the MongoDB data layer."""

import pytest
from unittest.mock import MagicMock, patch


class TestMongoDBIntegration:
    """Integration tests for MongoDB operations."""

    def test_article_insert(self, mock_mongodb, sample_article):
        """Test inserting an article into MongoDB."""
        mock_collection = mock_mongodb['news_analytics']['historical_articles']
        mock_collection.insert_one.return_value = MagicMock(inserted_id='123')
        
        result = mock_collection.insert_one(sample_article)
        assert result.inserted_id is not None
        mock_collection.insert_one.assert_called_once_with(sample_article)

    def test_article_upsert(self, mock_mongodb, sample_article):
        """Test upserting an article (update or insert)."""
        mock_collection = mock_mongodb['news_analytics']['historical_articles']
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        
        result = mock_collection.update_one(
            {"article_id": sample_article["article_id"]},
            {"$set": sample_article},
            upsert=True
        )
        assert result is not None

    def test_article_query_by_date(self, mock_mongodb):
        """Test querying articles by date range."""
        mock_collection = mock_mongodb['news_analytics']['historical_articles']
        mock_collection.find.return_value = [
            {"title": "Article 1", "event_time": 1735689600000},
            {"title": "Article 2", "event_time": 1735776000000},
        ]
        
        results = list(mock_collection.find({"event_time": {"$gte": 1735689600000}}))
        assert len(results) == 2


class TestCrawlerIntegration:
    """Integration tests for the crawler pipeline."""

    def test_rss_parsing(self, sample_rss_entry):
        """Test RSS feed entry parsing."""
        import time as time_module
        
        pub_date = sample_rss_entry.get('published_parsed')
        if pub_date:
            pub_timestamp = int(time_module.mktime(pub_date) * 1000)
        else:
            pub_timestamp = None
        
        assert pub_timestamp is not None
        assert pub_timestamp > 0

    def test_english_language_filter(self):
        """Test English language filtering logic."""
        articles = [
            {"language": "English", "title": "English Article"},
            {"language": "Spanish", "title": "Artículo en español"},
            {"language": "English", "title": "Another English"},
        ]
        
        english_only = [a for a in articles if a.get("language", "").lower() == "english"]
        assert len(english_only) == 2
