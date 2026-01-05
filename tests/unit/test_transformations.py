"""
Unit tests for Spark transformations and UDFs.

Uses pytest and local Spark session for testing.
Run with: pytest tests/unit/ -v
"""

import pytest
from pyspark.sql import SparkSession
import pyspark.sql.functions as F


@pytest.fixture(scope="module")
def spark():
    """Create a Spark session for testing."""
    spark = (
        SparkSession.builder
        .master("local[1]")
        .appName("UnitTests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield spark
    spark.stop()


class TestSparkUtils:
    """Tests for spark_utils module."""
    
    def test_simple_sentiment_positive(self, spark):
        """Test positive sentiment detection."""
        from jobs.utils.spark_utils import register_udfs
        
        udfs = register_udfs()
        df = spark.createDataFrame([
            ("Markets surge with strong growth and positive gains",),
        ], ["text"])
        
        result = df.withColumn("sentiment", udfs["sentiment"]("text")).collect()[0]
        
        assert result.sentiment.label == "pos"
        assert result.sentiment.polarity > 0
    
    def test_simple_sentiment_negative(self, spark):
        """Test negative sentiment detection."""
        from jobs.utils.spark_utils import register_udfs
        
        udfs = register_udfs()
        df = spark.createDataFrame([
            ("Stocks drop sharply amid decline and losses",),
        ], ["text"])
        
        result = df.withColumn("sentiment", udfs["sentiment"]("text")).collect()[0]
        
        assert result.sentiment.label == "neg"
        assert result.sentiment.polarity < 0
    
    def test_simple_sentiment_neutral(self, spark):
        """Test neutral sentiment detection."""
        from jobs.utils.spark_utils import register_udfs
        
        udfs = register_udfs()
        df = spark.createDataFrame([
            ("The weather is cloudy today with some rain expected",),
        ], ["text"])
        
        result = df.withColumn("sentiment", udfs["sentiment"]("text")).collect()[0]
        
        assert result.sentiment.label == "neu"
    
    def test_extract_keywords(self, spark):
        """Test keyword extraction."""
        from jobs.utils.spark_utils import register_udfs
        
        udfs = register_udfs()
        df = spark.createDataFrame([
            ("Apple announces new iPhone technology innovation",),
        ], ["text"])
        
        result = df.withColumn("keywords", udfs["keywords"]("text")).collect()[0]
        
        assert len(result.keywords) > 0
        terms = [kw.term for kw in result.keywords]
        assert "apple" in terms or "iphone" in terms or "technology" in terms
    
    def test_extract_entities(self, spark):
        """Test entity extraction."""
        from jobs.utils.spark_utils import register_udfs
        
        udfs = register_udfs()
        df = spark.createDataFrame([
            ("Apple Inc announced a partnership with Microsoft Corp today",),
        ], ["text"])
        
        result = df.withColumn("entities", udfs["entities"]("text")).collect()[0]
        
        assert len(result.entities) >= 1
        entity_texts = [e.text for e in result.entities]
        assert "Apple Inc" in entity_texts or "Microsoft Corp" in entity_texts


class TestJoinPatterns:
    """Tests for join_patterns module."""
    
    def test_broadcast_join_metadata(self, spark):
        """Test broadcast join enriches articles correctly."""
        from jobs.utils.join_patterns import broadcast_join_metadata
        
        articles = spark.createDataFrame([
            ("art1", "reuters.com"),
            ("art2", "bbc.com"),
        ], ["article_id", "source_domain"])
        
        metadata = spark.createDataFrame([
            ("reuters.com", "US", 0.95),
            ("bbc.com", "UK", 0.90),
        ], ["source_domain", "region", "credibility"])
        
        result = broadcast_join_metadata(articles, metadata)
        
        assert result.count() == 2
        assert "region" in result.columns
        assert "credibility" in result.columns
        
        reuters_row = result.filter(F.col("article_id") == "art1").collect()[0]
        assert reuters_row.region == "US"
        assert reuters_row.credibility == 0.95
    
    def test_sort_merge_join_large_tables(self, spark):
        """Test sort-merge join works correctly."""
        from jobs.utils.join_patterns import sort_merge_join_large_tables
        
        left = spark.createDataFrame([
            ("art1", 100),
            ("art2", 200),
            ("art3", 300),
        ], ["article_id", "views"])
        
        right = spark.createDataFrame([
            ("art1", "tech"),
            ("art2", "politics"),
        ], ["article_id", "category"])
        
        result = sort_merge_join_large_tables(left, right, ["article_id"], "inner")
        
        assert result.count() == 2  # art3 excluded (inner join)
        assert "views" in result.columns
        assert "category" in result.columns


class TestDataQuality:
    """Tests for data_quality module."""
    
    def test_validate_not_null_passes(self, spark):
        """Test not null validation passes for valid data."""
        from jobs.utils.data_quality import validate_not_null
        
        df = spark.createDataFrame([
            ("art1", "reuters.com"),
            ("art2", "bbc.com"),
        ], ["article_id", "source_domain"])
        
        result = validate_not_null(df, ["article_id", "source_domain"])
        
        assert result.passed is True
    
    def test_validate_not_null_fails(self, spark):
        """Test not null validation fails for null data."""
        from jobs.utils.data_quality import validate_not_null
        
        df = spark.createDataFrame([
            ("art1", "reuters.com"),
            (None, "bbc.com"),
        ], ["article_id", "source_domain"])
        
        result = validate_not_null(df, ["article_id"])
        
        assert result.passed is False
        assert result.details["null_counts"]["article_id"] == 1
    
    def test_validate_unique_passes(self, spark):
        """Test uniqueness validation passes for unique data."""
        from jobs.utils.data_quality import validate_unique
        
        df = spark.createDataFrame([
            ("art1", "hash1"),
            ("art2", "hash2"),
        ], ["article_id", "content_hash"])
        
        result = validate_unique(df, ["article_id"])
        
        assert result.passed is True
    
    def test_validate_unique_fails(self, spark):
        """Test uniqueness validation fails for duplicate data."""
        from jobs.utils.data_quality import validate_unique
        
        df = spark.createDataFrame([
            ("art1", "hash1"),
            ("art1", "hash2"),  # Duplicate article_id
        ], ["article_id", "content_hash"])
        
        result = validate_unique(df, ["article_id"])
        
        assert result.passed is False
        assert result.details["duplicate_rows"] == 1
    
    def test_validate_value_range(self, spark):
        """Test value range validation."""
        from jobs.utils.data_quality import validate_value_range
        
        df = spark.createDataFrame([
            (0.5,),
            (-0.3,),
            (1.5,),  # Out of range
        ], ["sentiment"])
        
        result = validate_value_range(df, "sentiment", min_val=-1.0, max_val=1.0)
        
        assert result.passed is False
        assert result.details["out_of_range_count"] == 1


class TestBatchTransformations:
    """Tests for batch pipeline transformations."""
    
    def test_pivot_aggregation(self, spark):
        """Test pivot operation for sentiment breakdown."""
        df = spark.createDataFrame([
            ("reuters.com", "positive"),
            ("reuters.com", "negative"),
            ("bbc.com", "positive"),
            ("bbc.com", "positive"),
        ], ["source_domain", "sentiment_label"])
        
        result = (
            df.groupBy("source_domain")
            .pivot("sentiment_label", ["positive", "negative", "neutral"])
            .count()
            .na.fill(0)
        )
        
        assert "positive" in result.columns
        assert "negative" in result.columns
        
        reuters = result.filter(F.col("source_domain") == "reuters.com").collect()[0]
        assert reuters.positive == 1
        assert reuters.negative == 1
    
    def test_window_ranking(self, spark):
        """Test window function ranking."""
        from pyspark.sql import Window
        
        df = spark.createDataFrame([
            ("reuters.com", 100),
            ("reuters.com", 200),
            ("bbc.com", 150),
        ], ["source_domain", "article_count"])
        
        window_spec = Window.partitionBy("source_domain").orderBy(F.desc("article_count"))
        result = df.withColumn("rank", F.rank().over(window_spec))
        
        # Check ranking within reuters.com
        reuters_top = result.filter(
            (F.col("source_domain") == "reuters.com") & 
            (F.col("rank") == 1)
        ).collect()[0]
        
        assert reuters_top.article_count == 200
