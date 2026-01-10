"""
GraphFrames Analytics for Entity Relationship Analysis.

Demonstrates graph processing with Spark:
- PageRank for entity influence scoring
- Connected components for topic clustering
- Motif finding for relationship patterns
- Breadth-first search for paths

Based on spark-lab/code/Advanced_Analytics_and_Machine_Learning-Chapter_30_Graph_Analysis.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import pyspark.sql.functions as F
from pyspark.sql import SparkSession, DataFrame
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML configuration."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_source_entity_graph(articles_df: DataFrame, spark: SparkSession):
    """
    Create a graph of sources to entities.
    
    Vertices: All unique sources + entities
    Edges: source -> entity relationships with weights
    
    Based on Chapter_30_Graph_Analysis.py pattern:
        stationVertices = bikeStations.withColumnRenamed("name", "id").distinct()
        tripEdges = tripData.withColumnRenamed("Start Station", "src")
    """
    try:
        from graphframes import GraphFrame
    except ImportError:
        import warnings
        warnings.warn(
            "graphframes not installed. Graph analytics will return empty results. "
            "Install with: pip install graphframes or "
            "--packages graphframes:graphframes:0.8.3-spark3.5-s_2.12",
            ImportWarning
        )
        # Return empty DataFrames with expected schema for graceful degradation
        empty_vertices = spark.createDataFrame([], "id STRING, type STRING")
        empty_edges = spark.createDataFrame([], "src STRING, dst STRING, weight DOUBLE")
        return empty_vertices, empty_edges, None
    
    # Extract source vertices
    source_vertices = (
        articles_df
        .select(F.col("source_domain").alias("id"))
        .distinct()
        .withColumn("type", F.lit("source"))
    )
    
    # Extract entity vertices (flatten entities array)
    entity_vertices = (
        articles_df
        .select(F.explode("entities").alias("entity"))
        .select(F.col("entity.norm").alias("id"))
        .distinct()
        .withColumn("type", F.lit("entity"))
    )
    
    # Combined vertices
    vertices = source_vertices.unionByName(entity_vertices).distinct()
    
    # Create edges: source -> entity
    edges = (
        articles_df
        .select(
            F.col("source_domain").alias("src"),
            F.explode("entities").alias("entity")
        )
        .select("src", F.col("entity.norm").alias("dst"))
        .groupBy("src", "dst")
        .agg(F.count("*").alias("weight"))
    )
    
    # Create GraphFrame
    graph = GraphFrame(vertices, edges)
    
    return graph, vertices, edges


def run_pagerank(graph, reset_prob: float = 0.15, max_iter: int = 10) -> DataFrame:
    """
    Run PageRank to find influential entities.
    
    Based on Chapter_30 pattern:
        ranks = stationGraph.pageRank(resetProbability=0.15, maxIter=10)
        ranks.vertices.orderBy(desc("pagerank")).select("id", "pagerank").show(10)
    """
    print("\n  Running PageRank algorithm...")
    ranks = graph.pageRank(resetProbability=reset_prob, maxIter=max_iter)
    
    top_entities = (
        ranks.vertices
        .orderBy(F.desc("pagerank"))
        .select("id", "type", "pagerank")
    )
    
    return top_entities


def run_connected_components(graph, spark: SparkSession) -> DataFrame:
    """
    Find connected components for topic clustering.
    
    Entities that frequently appear together form clusters.
    
    Based on Chapter_30 pattern:
        spark.sparkContext.setCheckpointDir("/tmp/checkpoints")
        cc = minGraph.connectedComponents()
    """
    print("\n  Running Connected Components...")
    
    # Set checkpoint directory (required for connected components)
    spark.sparkContext.setCheckpointDir("/tmp/graphframes_checkpoints")
    
    cc = graph.connectedComponents()
    
    # Count component sizes
    component_sizes = (
        cc
        .groupBy("component")
        .agg(F.count("*").alias("size"))
        .orderBy(F.desc("size"))
    )
    
    return cc, component_sizes


def find_triangles(graph) -> DataFrame:
    """
    Find triangular relationships (motifs).
    
    Useful for finding tightly connected entity clusters.
    
    Based on Chapter_30 pattern:
        motifs = stationGraph.find("(a)-[ab]->(b); (b)-[bc]->(c); (c)-[ca]->(a)")
    """
    print("\n  Finding Triangle Motifs...")
    
    # Find paths: a -> b -> c
    motifs = graph.find("(a)-[e1]->(b); (b)-[e2]->(c)")
    
    # Filter for interesting patterns
    triangles = (
        motifs
        .filter("a.id != c.id")  # Not the same node
        .select(
            F.col("a.id").alias("source"),
            F.col("b.id").alias("shared_entity"),
            F.col("c.id").alias("related_entity"),
            F.col("e1.weight").alias("weight_1"),
            F.col("e2.weight").alias("weight_2")
        )
    )
    
    return triangles


def compute_degree_metrics(graph) -> DataFrame:
    """
    Compute in-degree and out-degree for nodes.
    
    Based on Chapter_30 pattern:
        inDeg = stationGraph.inDegrees
        outDeg = stationGraph.outDegrees
        degreeRatio = inDeg.join(outDeg, "id")
    """
    print("\n  Computing Degree Metrics...")
    
    in_deg = graph.inDegrees
    out_deg = graph.outDegrees
    
    # Combine metrics
    degree_metrics = (
        in_deg
        .join(out_deg, "id", "outer")
        .na.fill(0)
        .withColumn(
            "degree_ratio",
            F.when(F.col("outDegree") > 0, 
                   F.col("inDegree") / F.col("outDegree"))
            .otherwise(F.col("inDegree"))
        )
    )
    
    return degree_metrics


def run_bfs(graph, from_vertex: str, to_vertex: str, max_path: int = 3) -> DataFrame:
    """
    Breadth-first search for shortest paths.
    
    Based on Chapter_30 pattern:
        stationGraph.bfs(fromExpr="id = 'Townsend at 7th'",
                         toExpr="id = 'Spear at Folsom'", maxPathLength=2)
    """
    print(f"\n  BFS: Finding path from '{from_vertex}' to '{to_vertex}'...")
    
    paths = graph.bfs(
        fromExpr=f"id = '{from_vertex}'",
        toExpr=f"id = '{to_vertex}'",
        maxPathLength=max_path
    )
    
    return paths


def main():
    """Main entry point for graph analytics."""
    parser = argparse.ArgumentParser(description="GraphFrames Analytics")
    parser.add_argument("--config", default="jobs/config/analytics-config.yaml")
    args = parser.parse_args()
    
    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        config = load_yaml(config_path)
    else:
        config = {}
    
    # Create Spark session with GraphFrames
    spark = (
        SparkSession.builder
        .appName("GraphAnalytics")
        # Add graphframes package
        .config("spark.jars.packages", 
                "graphframes:graphframes:0.8.3-spark3.5-s_2.12")
        .config("spark.sql.shuffle.partitions", 200)
        
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    
    print("=" * 70)
    print("GRAPH ANALYTICS - Entity Relationship Analysis")
    print("=" * 70)
    
    # Create sample data for demo
    print("\n[Step 1] Creating sample graph data...")
    
    # Sample articles with entities
    sample_data = [
        ("art1", "reuters.com", [
            {"type": "ORG", "text": "Apple Inc", "norm": "apple"},
            {"type": "ORG", "text": "Microsoft", "norm": "microsoft"}
        ]),
        ("art2", "bbc.com", [
            {"type": "ORG", "text": "Apple Inc", "norm": "apple"},
            {"type": "ORG", "text": "Google", "norm": "google"}
        ]),
        ("art3", "wsj.com", [
            {"type": "ORG", "text": "Microsoft", "norm": "microsoft"},
            {"type": "ORG", "text": "Amazon", "norm": "amazon"}
        ]),
        ("art4", "reuters.com", [
            {"type": "ORG", "text": "Google", "norm": "google"},
            {"type": "ORG", "text": "Amazon", "norm": "amazon"}
        ]),
        ("art5", "cnn.com", [
            {"type": "ORG", "text": "Tesla", "norm": "tesla"},
            {"type": "ORG", "text": "SpaceX", "norm": "spacex"}
        ]),
    ]
    
    from pyspark.sql.types import StructType, StructField, StringType, ArrayType
    
    entity_schema = ArrayType(StructType([
        StructField("type", StringType()),
        StructField("text", StringType()),
        StructField("norm", StringType())
    ]))
    
    schema = StructType([
        StructField("article_id", StringType()),
        StructField("source_domain", StringType()),
        StructField("entities", entity_schema)
    ])
    
    articles_df = spark.createDataFrame(sample_data, schema)
    articles_df.show(truncate=False)
    
    # Create graph
    print("\n[Step 2] Building Graph...")
    graph, vertices, edges = create_source_entity_graph(articles_df, spark)
    
    if graph is None:
        print("ERROR: GraphFrame creation failed. Exiting.")
        spark.stop()
        return
    
    print(f"  Vertices: {vertices.count()}")
    print(f"  Edges: {edges.count()}")
    
    vertices.show()
    edges.show()
    
    # Run analytics
    print("\n[Step 3] Running Graph Analytics...")
    
    # PageRank
    pagerank_results = run_pagerank(graph)
    print("\n  Top entities by PageRank:")
    pagerank_results.show(10)
    
    # Degree metrics
    degree_metrics = compute_degree_metrics(graph)
    print("\n  Degree Metrics:")
    degree_metrics.orderBy(F.desc("inDegree")).show(10)
    
    # Connected components
    cc, component_sizes = run_connected_components(graph, spark)
    print("\n  Component Sizes:")
    component_sizes.show()
    
    # Triangle motifs
    triangles = find_triangles(graph)
    print("\n  Triangular Relationships:")
    triangles.show(10, truncate=False)
    
    # Save results
    print("\n[Step 4] Saving Results...")
    output_path = config.get("outputs", {}).get("pagerank_path", "/tmp/output/graph")
    
    pagerank_results.write.mode("overwrite").parquet(f"{output_path}/pagerank")
    degree_metrics.write.mode("overwrite").parquet(f"{output_path}/degrees")
    
    print("\n" + "=" * 70)
    print("GRAPH ANALYTICS COMPLETED")
    print("=" * 70)
    
    spark.stop()


if __name__ == "__main__":
    main()
