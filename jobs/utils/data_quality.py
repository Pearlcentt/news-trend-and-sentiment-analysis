"""
Data Quality Validation Framework.

Provides validation functions for news pipeline data:
- Schema validation
- Null/empty field checks
- Deduplication verification
- Data freshness monitoring
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession


class DataQualityResult:
    """Container for data quality check results."""
    
    def __init__(self, check_name: str, passed: bool, details: Dict[str, Any]):
        self.check_name = check_name
        self.passed = passed
        self.details = details
        self.timestamp = datetime.now()
    
    def __repr__(self):
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        return f"{self.check_name}: {status} - {self.details}"


def validate_not_null(
    df: DataFrame,
    columns: List[str],
    sample_size: int = 5
) -> DataQualityResult:
    """
    Check that specified columns have no null values.
    
    Args:
        df: DataFrame to validate
        columns: List of column names that should not be null
        sample_size: Number of invalid rows to sample for debugging
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    null_counts = {}
    total_rows = df.count()
    
    for col in columns:
        null_count = df.filter(F.col(col).isNull()).count()
        if null_count > 0:
            null_counts[col] = null_count
    
    passed = len(null_counts) == 0
    
    details = {
        "total_rows": total_rows,
        "columns_checked": columns,
        "null_counts": null_counts,
        "null_percentage": {k: v/total_rows*100 for k, v in null_counts.items()}
    }
    
    return DataQualityResult("NotNull Check", passed, details)


def validate_not_empty(
    df: DataFrame,
    columns: List[str],
    min_length: int = 1
) -> DataQualityResult:
    """
    Check that string columns are not empty.
    
    Args:
        df: DataFrame to validate
        columns: List of string column names
        min_length: Minimum required string length
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    empty_counts = {}
    total_rows = df.count()
    
    for col in columns:
        empty_count = df.filter(
            (F.col(col).isNull()) | 
            (F.length(F.trim(F.col(col))) < min_length)
        ).count()
        if empty_count > 0:
            empty_counts[col] = empty_count
    
    passed = len(empty_counts) == 0
    
    details = {
        "total_rows": total_rows,
        "min_length": min_length,
        "columns_checked": columns,
        "empty_counts": empty_counts
    }
    
    return DataQualityResult("NotEmpty Check", passed, details)


def validate_unique(
    df: DataFrame,
    columns: List[str]
) -> DataQualityResult:
    """
    Check that specified columns form a unique key.
    
    Args:
        df: DataFrame to validate
        columns: List of columns that should be unique together
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    total_rows = df.count()
    distinct_rows = df.select(*columns).distinct().count()
    
    duplicates = total_rows - distinct_rows
    passed = duplicates == 0
    
    # Sample duplicates if any
    duplicate_sample = []
    if not passed:
        dup_df = (
            df.groupBy(*columns)
            .count()
            .filter(F.col("count") > 1)
            .limit(5)
        )
        duplicate_sample = [row.asDict() for row in dup_df.collect()]
    
    details = {
        "total_rows": total_rows,
        "distinct_rows": distinct_rows,
        "duplicate_rows": duplicates,
        "columns": columns,
        "duplicate_sample": duplicate_sample
    }
    
    return DataQualityResult("Uniqueness Check", passed, details)


def validate_freshness(
    df: DataFrame,
    timestamp_col: str,
    max_age_hours: int = 24
) -> DataQualityResult:
    """
    Check that data is fresh (within specified time window).
    
    Args:
        df: DataFrame to validate
        timestamp_col: Name of timestamp column
        max_age_hours: Maximum allowed age in hours
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    now = datetime.now()
    cutoff = now - timedelta(hours=max_age_hours)
    
    stats = df.agg(
        F.max(timestamp_col).alias("latest"),
        F.min(timestamp_col).alias("oldest"),
        F.count("*").alias("total_rows")
    ).collect()[0]
    
    latest = stats["latest"]
    passed = latest is not None and latest >= cutoff
    
    details = {
        "timestamp_column": timestamp_col,
        "latest_record": str(latest),
        "oldest_record": str(stats["oldest"]),
        "max_age_hours": max_age_hours,
        "cutoff_time": str(cutoff),
        "total_rows": stats["total_rows"]
    }
    
    return DataQualityResult("Freshness Check", passed, details)


def validate_value_range(
    df: DataFrame,
    column: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
) -> DataQualityResult:
    """
    Check that numeric values are within expected range.
    
    Args:
        df: DataFrame to validate
        column: Numeric column to check
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    # Build filter condition
    out_of_range_filter = F.lit(False)
    if min_val is not None:
        out_of_range_filter = out_of_range_filter | (F.col(column) < min_val)
    if max_val is not None:
        out_of_range_filter = out_of_range_filter | (F.col(column) > max_val)
    
    out_of_range_count = df.filter(out_of_range_filter).count()
    total_rows = df.count()
    
    passed = out_of_range_count == 0
    
    # Get actual min/max
    actual_stats = df.agg(
        F.min(column).alias("actual_min"),
        F.max(column).alias("actual_max")
    ).collect()[0]
    
    details = {
        "column": column,
        "expected_min": min_val,
        "expected_max": max_val,
        "actual_min": actual_stats["actual_min"],
        "actual_max": actual_stats["actual_max"],
        "out_of_range_count": out_of_range_count,
        "total_rows": total_rows
    }
    
    return DataQualityResult("Value Range Check", passed, details)


def validate_referential_integrity(
    df: DataFrame,
    foreign_key_col: str,
    reference_df: DataFrame,
    reference_col: str
) -> DataQualityResult:
    """
    Check referential integrity between DataFrames.
    
    Args:
        df: DataFrame with foreign key
        foreign_key_col: Column name in df
        reference_df: Reference DataFrame
        reference_col: Column name in reference_df
        
    Returns:
        DataQualityResult with pass/fail and details
    """
    # Get all foreign key values
    fk_values = df.select(foreign_key_col).distinct()
    ref_values = reference_df.select(reference_col).distinct()
    
    # Find orphaned keys
    orphaned = fk_values.join(
        ref_values,
        fk_values[foreign_key_col] == ref_values[reference_col],
        "left_anti"
    )
    
    orphan_count = orphaned.count()
    passed = orphan_count == 0
    
    orphan_sample = [row[0] for row in orphaned.limit(10).collect()]
    
    details = {
        "foreign_key_column": foreign_key_col,
        "reference_column": reference_col,
        "orphaned_count": orphan_count,
        "orphan_sample": orphan_sample
    }
    
    return DataQualityResult("Referential Integrity Check", passed, details)


class DataQualityValidator:
    """
    Orchestrator for running multiple data quality checks.
    """
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.results: List[DataQualityResult] = []
    
    def run_all_checks(
        self,
        df: DataFrame,
        not_null_cols: List[str] = None,
        not_empty_cols: List[str] = None,
        unique_cols: List[str] = None,
        timestamp_col: str = None
    ) -> List[DataQualityResult]:
        """
        Run all applicable data quality checks.
        
        Returns list of DataQualityResult objects.
        """
        self.results = []
        
        if not_null_cols:
            self.results.append(validate_not_null(df, not_null_cols))
        
        if not_empty_cols:
            self.results.append(validate_not_empty(df, not_empty_cols))
        
        if unique_cols:
            self.results.append(validate_unique(df, unique_cols))
        
        if timestamp_col:
            self.results.append(validate_freshness(df, timestamp_col))
        
        return self.results
    
    def print_report(self):
        """Print human-readable quality report."""
        print("=" * 60)
        print("DATA QUALITY REPORT")
        print("=" * 60)
        
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        
        for result in self.results:
            print(f"\n{result}")
        
        print("\n" + "-" * 60)
        print(f"Summary: {passed} passed, {failed} failed")
        print("=" * 60)
        
        return failed == 0
    
    def to_dataframe(self) -> DataFrame:
        """Convert results to DataFrame for persistence."""
        rows = [
            (r.check_name, r.passed, str(r.details), str(r.timestamp))
            for r in self.results
        ]
        return self.spark.createDataFrame(
            rows,
            ["check_name", "passed", "details", "timestamp"]
        )


# Demo function
def demo_data_quality(spark: SparkSession):
    """Demonstrate data quality validation."""
    
    # Sample data
    df = spark.createDataFrame([
        ("art1", "reuters.com", "Title 1", 0.5, "2025-01-15 10:00:00"),
        ("art2", "bbc.com", "Title 2", 0.3, "2025-01-15 11:00:00"),
        ("art3", "wsj.com", "", -0.2, "2025-01-15 12:00:00"),  # Empty title
        ("art4", "reuters.com", "Title 4", 1.5, "2025-01-15 13:00:00"),  # Out of range
        ("art1", "reuters.com", "Title 1 dup", 0.5, "2025-01-15 14:00:00"),  # Duplicate ID
    ], ["article_id", "source_domain", "title", "sentiment", "event_ts"])
    
    df = df.withColumn("event_ts", F.to_timestamp("event_ts"))
    
    print("\nSample Data:")
    df.show()
    
    # Run checks
    validator = DataQualityValidator(spark)
    
    results = [
        validate_not_null(df, ["article_id", "source_domain"]),
        validate_not_empty(df, ["title"]),
        validate_unique(df, ["article_id"]),
        validate_value_range(df, "sentiment", min_val=-1.0, max_val=1.0),
    ]
    
    validator.results = results
    validator.print_report()


if __name__ == "__main__":
    spark = SparkSession.builder.appName("DataQualityDemo").getOrCreate()
    demo_data_quality(spark)
    spark.stop()
