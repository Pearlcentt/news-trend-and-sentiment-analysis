"""
Shared Spark utility functions and UDFs.

Provides reusable components for both batch and streaming pipelines.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List

import pyspark.sql.functions as F
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


# =============================================================================
# STOPWORDS
# =============================================================================

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "about", "into", "after", "their", "they", "been", "was", "were",
    "said", "over", "upon", "would", "could", "should", "more", "than",
}


# =============================================================================
# NLP UDFs - Import from unified sentiment module
# =============================================================================

# Import from unified sentiment module to avoid code duplication
from .sentiment import analyze_sentiment as simple_sentiment


def extract_keywords(text: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Extract top-k keywords by frequency.
    
    Returns list of {term, score} dicts.
    """
    if not text:
        return []
    
    tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", text)]
    filtered = [t for t in tokens if t not in STOPWORDS]
    counts = Counter(filtered)
    total = sum(counts.values()) or 1
    
    keywords = counts.most_common(top_k)
    return [{"term": term, "score": round(freq / total, 4)} for term, freq in keywords]


def extract_entities(text: str) -> List[Dict[str, str]]:
    """
    Simple named entity extraction using capitalization patterns.
    
    Returns list of {type, text, norm} dicts.
    """
    if not text:
        return []
    
    # Match capitalized word sequences (e.g., "United States", "Apple Inc")
    matches = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    unique = list(dict.fromkeys(matches))
    
    return [
        {"type": "ORG", "text": entity, "norm": entity.lower().replace(" ", "_")}
        for entity in unique[:10]  # Limit to 10
    ]


def derive_topics(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Derive topic IDs from keywords using deterministic hash.
    
    Uses MD5 to ensure consistent topic IDs across sessions
    (Python's hash() is randomized per PEP 456).
    
    Returns list of {topic_id, score} dicts.
    """
    import hashlib
    
    if not keywords:
        return []
    
    topics = []
    for kw in keywords:
        # Use MD5 for deterministic cross-session hash
        term_hash = hashlib.md5(kw["term"].encode()).hexdigest()
        topic_id = int(term_hash[:8], 16) % 1000  # Deterministic 0-999
        topics.append({"topic_id": topic_id, "score": kw["score"]})
    
    return topics


# =============================================================================
# UDF Registration
# =============================================================================

def get_udf_schemas():
    """Get schema definitions for UDFs."""
    return {
        "sentiment": StructType([
            StructField("label", StringType()),
            StructField("polarity", DoubleType())
        ]),
        "keywords": ArrayType(StructType([
            StructField("term", StringType()),
            StructField("score", DoubleType())
        ])),
        "entities": ArrayType(StructType([
            StructField("type", StringType()),
            StructField("text", StringType()),
            StructField("norm", StringType())
        ])),
        "topics": ArrayType(StructType([
            StructField("topic_id", IntegerType()),
            StructField("score", DoubleType())
        ]))
    }


def register_udfs():
    """Register all UDFs and return registry dict."""
    schemas = get_udf_schemas()
    
    return {
        "sentiment": F.udf(simple_sentiment, schemas["sentiment"]),
        "keywords": F.udf(extract_keywords, schemas["keywords"]),
        "entities": F.udf(extract_entities, schemas["entities"]),
        "topics": F.udf(derive_topics, schemas["topics"]),
    }


# =============================================================================
# Performance Utilities
# =============================================================================

def optimize_for_join(df, partition_col: str, num_partitions: int = 200):
    """Repartition DataFrame for optimized joins."""
    return df.repartition(num_partitions, partition_col)


def coalesce_output(df, target_files: int = 10):
    """Coalesce DataFrame to reduce output file count."""
    return df.coalesce(target_files)


def cache_if_reused(df, min_actions: int = 2):
    """
    Utility to remind about caching strategy.
    
    Cache a DataFrame if it will be used in multiple actions.
    """
    from pyspark import StorageLevel
    return df.persist(StorageLevel.MEMORY_AND_DISK)
