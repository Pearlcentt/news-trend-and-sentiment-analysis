"""
Join Patterns Module for Spark Pipeline.

Demonstrates all course-required join operations:
- Broadcast joins for small tables (source metadata)
- Sort-merge joins for large-scale data
- Multiple join optimization strategies

Based on patterns from IT4931 spark-lab (Chapter 8 - Joins).
"""

from __future__ import annotations

from typing import List, Optional

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, SparkSession


def broadcast_join_metadata(
    articles_df: DataFrame,
    metadata_df: DataFrame,
    join_key: str = "source_domain",
    metadata_cols: Optional[List[str]] = None
) -> DataFrame:
    """
    Broadcast join for enriching articles with source metadata.
    
    Use when metadata table is small (<= broadcast threshold, typically 10MB-256MB).
    Avoids shuffle by broadcasting small table to all executors.
    
    Example from spark-lab/code/Structured_APIs-Chapter_8_Joins.py:
        enriched = articles.join(broadcast(source_metadata), on="source_domain", how="left")
    
    Args:
        articles_df: Large articles DataFrame
        metadata_df: Small metadata DataFrame (will be broadcast)
        join_key: Column to join on
        metadata_cols: Optional list of columns to select from metadata
        
    Returns:
        Enriched DataFrame with metadata columns
    """
    if metadata_cols:
        metadata_df = metadata_df.select(join_key, *metadata_cols)
    
    # Force broadcast hint for small table
    enriched = articles_df.join(
        F.broadcast(metadata_df),
        on=join_key,
        how="left"
    )
    
    return enriched


def sort_merge_join_large_tables(
    left_df: DataFrame,
    right_df: DataFrame,
    join_keys: List[str],
    how: str = "inner"
) -> DataFrame:
    """
    Sort-merge join for large tables.
    
    Use for large-to-large joins when broadcast is not feasible.
    Hint forces sort-merge strategy even if optimizer chooses otherwise.
    
    Example from spark-lab:
        large_join = articles.hint("merge").join(
            historical_data.hint("merge"),
            on=["article_id"],
            how="inner"
        )
    
    Args:
        left_df: Left DataFrame
        right_df: Right DataFrame  
        join_keys: List of columns to join on
        how: Join type (inner, left, right, outer)
        
    Returns:
        Joined DataFrame
    """
    return (
        left_df.hint("merge")
        .join(
            right_df.hint("merge"),
            on=join_keys,
            how=how
        )
    )


def multi_table_join(
    base_df: DataFrame,
    join_specs: List[dict]
) -> DataFrame:
    """
    Optimized multi-table join with automatic hint selection.
    
    Args:
        base_df: Base DataFrame to start from
        join_specs: List of join specifications:
            [
                {"df": df1, "keys": ["col"], "how": "left", "broadcast": True},
                {"df": df2, "keys": ["col1", "col2"], "how": "inner", "broadcast": False}
            ]
    
    Returns:
        Joined DataFrame with all tables
    """
    result = base_df
    
    for spec in join_specs:
        df_to_join = spec["df"]
        keys = spec["keys"]
        how = spec.get("how", "inner")
        use_broadcast = spec.get("broadcast", False)
        
        if use_broadcast:
            result = result.join(F.broadcast(df_to_join), on=keys, how=how)
        else:
            result = result.join(df_to_join, on=keys, how=how)
    
    return result


def array_contains_join(
    articles_df: DataFrame,
    entities_df: DataFrame,
    array_col: str = "tags",
    entity_col: str = "entity_name"
) -> DataFrame:
    """
    Join using array_contains for array membership.
    
    Example from spark-lab:
        tagged = articles.join(
            entities,
            expr("array_contains(tags, entity_name)")
        )
    
    Args:
        articles_df: DataFrame with array column
        entities_df: DataFrame with entity values
        array_col: Name of array column in articles
        entity_col: Name of entity column
        
    Returns:
        Joined DataFrame where entity is in array
    """
    from pyspark.sql.functions import expr
    
    return articles_df.join(
        entities_df,
        expr(f"array_contains({array_col}, {entity_col})")
    )


def cross_join_with_filter(
    left_df: DataFrame,
    right_df: DataFrame,
    filter_condition: str
) -> DataFrame:
    """
    Cross join with filter for complex join conditions.
    
    Use sparingly - can be expensive. Filter should reduce output significantly.
    
    Args:
        left_df: Left DataFrame
        right_df: Right DataFrame (should be small)
        filter_condition: SQL expression to filter results
        
    Returns:
        Filtered cross join result
    """
    return (
        left_df
        .crossJoin(F.broadcast(right_df))
        .filter(filter_condition)
    )


# =============================================================================
# Demo Functions
# =============================================================================

def demo_join_patterns(spark: SparkSession):
    """Demonstrate all join patterns with sample data."""
    
    # Sample data
    articles = spark.createDataFrame([
        ("art1", "reuters.com", ["tech", "stocks"], 0.5),
        ("art2", "bbc.com", ["politics", "economy"], -0.2),
        ("art3", "wsj.com", ["tech", "ai"], 0.8),
        ("art4", "reuters.com", ["economy"], 0.1),
    ], ["article_id", "source_domain", "tags", "sentiment"])
    
    source_metadata = spark.createDataFrame([
        ("reuters.com", "US", "tier1", 0.95),
        ("bbc.com", "UK", "tier1", 0.90),
        ("wsj.com", "US", "tier2", 0.85),
    ], ["source_domain", "region", "tier", "credibility"])
    
    entities = spark.createDataFrame([
        ("tech", "Technology"),
        ("economy", "Business"),
        ("politics", "Government"),
    ], ["entity_name", "category"])
    
    print("=" * 60)
    print("JOIN PATTERNS DEMONSTRATION")
    print("=" * 60)
    
    # 1. Broadcast join
    print("\n1. BROADCAST JOIN (source metadata enrichment):")
    enriched = broadcast_join_metadata(articles, source_metadata)
    enriched.show()
    
    # 2. Array contains join
    print("\n2. ARRAY CONTAINS JOIN (entity tagging):")
    tagged = array_contains_join(articles, entities)
    tagged.show()
    
    # 3. Multi-table join
    print("\n3. MULTI-TABLE JOIN (optimized):")
    multi_joined = multi_table_join(
        articles,
        [
            {"df": source_metadata, "keys": ["source_domain"], "how": "left", "broadcast": True},
        ]
    )
    multi_joined.show()
    
    print("=" * 60)
    print("JOIN PATTERNS DEMO COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    spark = (
        SparkSession.builder
        .appName("JoinPatternsDemo")
        
        .getOrCreate()
    )
    
    demo_join_patterns(spark)
    spark.stop()
