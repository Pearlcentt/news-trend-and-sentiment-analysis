"""Test configuration and fixtures for the news pipeline tests."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_mongodb():
    """Create a mock MongoDB client."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    return mock_client


@pytest.fixture
def sample_article():
    """Sample article data for testing."""
    return {
        "article_id": "test_123",
        "title": "Test Article Title",
        "url": "https://example.com/article",
        "body_text": "This is a test article content.",
        "source_domain": "example.com",
        "published_at": int(datetime.now().timestamp() * 1000),
        "event_time": int(datetime.now().timestamp() * 1000),
        "sentiment": "neutral",
        "category": "Technology",
    }


@pytest.fixture
def sample_rss_entry():
    """Sample RSS feed entry for testing."""
    return {
        "title": "Sample RSS Article",
        "link": "https://bbc.com/news/test",
        "summary": "This is a sample RSS article summary.",
        "published_parsed": (2025, 1, 15, 10, 30, 0, 0, 0, 0),
    }


@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer."""
    with patch('confluent_kafka.Producer') as mock:
        yield mock
