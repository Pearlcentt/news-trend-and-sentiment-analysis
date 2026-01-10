"""
Integration tests for the news pipeline.

Tests end-to-end data flow through the pipeline components.
Run with: pytest tests/integration/ -v
"""

import pytest
from pyspark.sql import SparkSession
import pyspark.sql.functions as F


@pytest.fixture(scope="module")
def spark():
    """Create Spark session for integration tests."""
    import sys
    import os
    # Ensure jobs/ is in path
    jobs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../jobs'))
    if jobs_path not in sys.path:
        sys.path.insert(0, jobs_path)
        
    spark = (
        SparkSession.builder
        .master("local[2]")
        .appName("IntegrationTests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield spark
    spark.stop()


class TestBatchPipeline:
    """Integration tests for batch processing pipeline."""
    
    def test_full_batch_workflow(self, spark):
        """Test complete batch processing workflow."""
        # Simulate raw articles
        raw_articles = spark.createDataFrame([
            ("art1", "reuters.com", "Tech stocks surge amid positive growth", "en", 1705334400000),
            ("art2", "bbc.com", "Markets decline on trade concerns", "en", 1705334460000),
            ("art3", "wsj.com", "Economy shows mixed signals today", "en", 1705334520000),
            ("art4", "reuters.com", "Healthcare sector rises strongly", "en", 1705334580000),
        ], ["article_id", "source_domain", "body_text", "language", "event_time"])
        
        # Apply transformations (simplified batch pipeline)
        processed = (
            raw_articles
            .withColumn("event_ts", (F.col("event_time") / 1000).cast("timestamp"))
            .withColumn("dt", F.date_format("event_ts", "yyyy-MM-dd"))
            .withColumn("word_count", F.size(F.split("body_text", " ")))
        )
        
        # Verify transformations
        assert processed.count() == 4
        assert "dt" in processed.columns
        assert "word_count" in processed.columns
        
        # Test aggregations
        daily_stats = (
            processed
            .groupBy("dt", "source_domain")
            .agg(
                F.count("*").alias("article_count"),
                F.avg("word_count").alias("avg_words")
            )
        )
        
        assert daily_stats.count() > 0
        
        # Test pivot
        source_pivot = (
            daily_stats
            .groupBy("dt")
            .pivot("source_domain")
            .agg(F.sum("article_count"))
            .na.fill(0)
        )
        
        assert "reuters.com" in source_pivot.columns or "bbc.com" in source_pivot.columns
    
    def test_window_functions(self, spark):
        """Test window function aggregations."""
        from pyspark.sql import Window
        
        # Sample time series
        data = spark.createDataFrame([
            ("2025-01-15", "reuters.com", 100),
            ("2025-01-16", "reuters.com", 120),
            ("2025-01-17", "reuters.com", 90),
            ("2025-01-18", "reuters.com", 150),
        ], ["dt", "source_domain", "article_count"])
        
        window_spec = Window.partitionBy("source_domain").orderBy("dt").rowsBetween(-2, 0)
        
        result = data.withColumn(
            "rolling_avg",
            F.avg("article_count").over(window_spec)
        )
        
        # Check rolling average is computed
        assert result.filter(F.col("dt") == "2025-01-18").first().rolling_avg is not None
    
    def test_cube_aggregation(self, spark):
        """Test cube multi-dimensional aggregation."""
        data = spark.createDataFrame([
            ("2025-01-15", "reuters.com", "en", 10),
            ("2025-01-15", "bbc.com", "en", 15),
            ("2025-01-16", "reuters.com", "en", 12),
        ], ["dt", "source_domain", "language", "count"])
        
        cube_result = (
            data
            .cube("dt", "source_domain")
            .agg(F.sum("count").alias("total"))
        )
        
        # Cube creates all combinations including nulls (grand totals)
        assert cube_result.count() > data.count()
        
        # Grand total should exist (where both dt and source_domain are null)
        grand_total = cube_result.filter(
            F.col("dt").isNull() & F.col("source_domain").isNull()
        ).collect()
        
        assert len(grand_total) == 1
        assert grand_total[0].total == 37  # 10 + 15 + 12


class TestDataQualityIntegration:
    """Integration tests for data quality validation."""
    
    def test_quality_check_pipeline(self, spark):
        """Test full data quality validation workflow."""
        from jobs.utils.data_quality import DataQualityValidator
        
        # Sample data with some issues
        data = spark.createDataFrame([
            ("art1", "reuters.com", "Title 1", 0.5),
            ("art2", "bbc.com", "Title 2", 0.3),
            ("art3", "wsj.com", "", -0.2),  # Empty title
            (None, "cnn.com", "Title 4", 0.1),  # Null article_id
        ], ["article_id", "source_domain", "title", "sentiment"])
        
        validator = DataQualityValidator(spark)
        results = validator.run_all_checks(
            data,
            not_null_cols=["article_id"],
            not_empty_cols=["title"],
            unique_cols=["article_id"]
        )
        
        # Should have 3 check results
        assert len(results) == 3
        
        # Not null check should fail
        not_null_result = next(r for r in results if "NotNull" in r.check_name)
        assert not_null_result.passed is False
        
        # Not empty check should fail
        not_empty_result = next(r for r in results if "NotEmpty" in r.check_name)
        assert not_empty_result.passed is False


class TestJoinIntegration:
    """Integration tests for join operations."""
    
    def test_metadata_enrichment_pipeline(self, spark):
        """Test full metadata enrichment workflow."""
        from jobs.utils.join_patterns import broadcast_join_metadata
        
        # Articles stream
        articles = spark.createDataFrame([
            ("art1", "reuters.com", "Breaking news from Reuters"),
            ("art2", "bbc.com", "BBC World Service update"),
            ("art3", "unknown.com", "From unknown source"),
        ], ["article_id", "source_domain", "title"])
        
        # Source metadata
        metadata = spark.createDataFrame([
            ("reuters.com", "US", "tier1", 0.95),
            ("bbc.com", "UK", "tier1", 0.90),
        ], ["source_domain", "region", "tier", "credibility"])
        
        # Enrich
        enriched = broadcast_join_metadata(articles, metadata)
        
        # All articles should be preserved (left join)
        assert enriched.count() == 3
        
        # Unknown source should have null metadata
        unknown_row = enriched.filter(F.col("source_domain") == "unknown.com").first()
        assert unknown_row.region is None
        
        # Known sources should have metadata
        reuters_row = enriched.filter(F.col("source_domain") == "reuters.com").first()
        assert reuters_row.region == "US"
        assert reuters_row.credibility == 0.95
