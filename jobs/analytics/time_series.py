"""
Time Series Analysis for News Trends.

Demonstrates time series processing:
- Rolling window statistics
- Trend detection
- Seasonality analysis
- Anomaly detection for breaking news

Patterns based on spark-lab aggregation and windowing.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict

import pyspark.sql.functions as F
from pyspark.sql import SparkSession, DataFrame, Window
import yaml


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML configuration."""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_rolling_statistics(
    df: DataFrame,
    partition_cols: list,
    order_col: str,
    value_col: str,
    windows: list = [7, 14, 30]
) -> DataFrame:
    """
    Compute rolling statistics for multiple window sizes.
    
    Based on Chapter_7_Aggregations.py window patterns.
    """
    result = df
    
    for window_size in windows:
        window_spec = (
            Window
            .partitionBy(*partition_cols)
            .orderBy(order_col)
            .rowsBetween(-window_size + 1, 0)
        )
        
        result = (
            result
            .withColumn(f"rolling_{window_size}d_avg", 
                       F.avg(value_col).over(window_spec))
            .withColumn(f"rolling_{window_size}d_std",
                       F.stddev_pop(value_col).over(window_spec))
            .withColumn(f"rolling_{window_size}d_min",
                       F.min(value_col).over(window_spec))
            .withColumn(f"rolling_{window_size}d_max",
                       F.max(value_col).over(window_spec))
            .withColumn(f"rolling_{window_size}d_count",
                       F.count(value_col).over(window_spec))
        )
    
    return result


def detect_trend(
    df: DataFrame,
    order_col: str,
    value_col: str,
    lookback: int = 7
) -> DataFrame:
    """
    Detect trend direction using simple moving average comparison.
    
    Trend types:
    - "uptrend": Current value > MA
    - "downtrend": Current value < MA  
    - "sideways": Within 5% of MA
    """
    window_spec = (
        Window
        .orderBy(order_col)
        .rowsBetween(-lookback + 1, 0)
    )
    
    result = (
        df
        .withColumn("ma", F.avg(value_col).over(window_spec))
        .withColumn("deviation", 
                   (F.col(value_col) - F.col("ma")) / F.col("ma"))
        .withColumn("trend",
                   F.when(F.col("deviation") > 0.05, "uptrend")
                    .when(F.col("deviation") < -0.05, "downtrend")
                    .otherwise("sideways"))
    )
    
    return result


def detect_anomalies(
    df: DataFrame,
    partition_cols: list,
    order_col: str,
    value_col: str,
    window_size: int = 30,
    z_threshold: float = 2.5
) -> DataFrame:
    """
    Detect anomalies using Z-score method.
    
    Points with Z-score > threshold are flagged as anomalies.
    Useful for detecting breaking news (unusual activity spikes).
    """
    window_spec = (
        Window
        .partitionBy(*partition_cols)
        .orderBy(order_col)
        .rowsBetween(-window_size + 1, -1)  # Exclude current row
    )
    
    result = (
        df
        .withColumn("historical_mean", F.avg(value_col).over(window_spec))
        .withColumn("historical_std", F.stddev_pop(value_col).over(window_spec))
        .withColumn("z_score",
                   F.when(F.col("historical_std") > 0,
                         (F.col(value_col) - F.col("historical_mean")) / F.col("historical_std"))
                   .otherwise(0))
        .withColumn("is_anomaly", F.abs(F.col("z_score")) > z_threshold)
        .withColumn("anomaly_type",
                   F.when(F.col("z_score") > z_threshold, "spike")
                    .when(F.col("z_score") < -z_threshold, "drop")
                    .otherwise("normal"))
    )
    
    return result


def compute_velocity_acceleration(
    df: DataFrame,
    order_col: str,
    value_col: str
) -> DataFrame:
    """
    Compute velocity (rate of change) and acceleration (change in velocity).
    
    Velocity: first derivative (change from previous period)
    Acceleration: second derivative (change in velocity)
    """
    lag_window = Window.orderBy(order_col)
    
    result = (
        df
        # Velocity: current - previous
        .withColumn("prev_value", F.lag(value_col, 1).over(lag_window))
        .withColumn("velocity", F.col(value_col) - F.col("prev_value"))
        # Acceleration: change in velocity
        .withColumn("prev_velocity", F.lag("velocity", 1).over(lag_window))
        .withColumn("acceleration", F.col("velocity") - F.col("prev_velocity"))
        # Percentage changes
        .withColumn("pct_change",
                   F.when(F.col("prev_value") != 0,
                         (F.col(value_col) - F.col("prev_value")) / F.abs(F.col("prev_value")) * 100)
                   .otherwise(0))
    )
    
    return result


def compute_seasonality(
    df: DataFrame,
    date_col: str,
    value_col: str
) -> DataFrame:
    """
    Extract seasonality components from date.
    
    Useful for understanding weekly/monthly patterns.
    """
    result = (
        df
        .withColumn("day_of_week", F.dayofweek(date_col))
        .withColumn("day_of_month", F.dayofmonth(date_col))
        .withColumn("week_of_year", F.weekofyear(date_col))
        .withColumn("month", F.month(date_col))
        .withColumn("is_weekend", 
                   F.when(F.col("day_of_week").isin([1, 7]), True)
                    .otherwise(False))
    )
    
    return result


def main():
    """Main entry point for time series analysis."""
    parser = argparse.ArgumentParser(description="Time Series Analysis")
    parser.add_argument("--config", default="jobs/config/analytics-config.yaml")
    args = parser.parse_args()
    
    # Create Spark session
    spark = (
        SparkSession.builder
        .appName("TimeSeriesAnalysis")
        .config("spark.sql.shuffle.partitions", 200)
        
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    
    print("=" * 70)
    print("TIME SERIES ANALYSIS - News Trends")
    print("=" * 70)
    
    # Create sample daily aggregated data
    print("\n[Step 1] Creating Sample Time Series Data...")
    
    from datetime import date, timedelta
    
    # Generate 60 days of data
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(60)]
    
    import random
    random.seed(42)
    
    data = [
        (d.isoformat(), 
         "reuters.com",
         100 + random.randint(-20, 20) + (10 if d.weekday() < 5 else -30),  # Article count
         0.05 + random.uniform(-0.1, 0.1))  # Sentiment
        for d in dates
    ]
    
    # Add some anomalies
    data[15] = (dates[15].isoformat(), "reuters.com", 250, 0.3)  # Spike
    data[40] = (dates[40].isoformat(), "reuters.com", 30, -0.2)   # Drop
    
    df = spark.createDataFrame(data, ["dt", "source_domain", "article_count", "avg_sentiment"])
    df = df.withColumn("dt", F.to_date("dt"))
    
    print(f"  Generated {df.count()} daily records")
    df.show(10)
    
    # Compute rolling statistics
    print("\n[Step 2] Computing Rolling Statistics...")
    
    rolling_df = compute_rolling_statistics(
        df,
        partition_cols=["source_domain"],
        order_col="dt",
        value_col="article_count",
        windows=[7, 14, 30]
    )
    
    rolling_df.select(
        "dt", "article_count",
        "rolling_7d_avg", "rolling_14d_avg", "rolling_30d_avg"
    ).show(10)
    
    # Detect trends
    print("\n[Step 3] Detecting Trends...")
    
    trend_df = detect_trend(
        rolling_df,
        order_col="dt",
        value_col="article_count",
        lookback=7
    )
    
    trend_df.select("dt", "article_count", "ma", "deviation", "trend").show(15)
    
    # Detect anomalies
    print("\n[Step 4] Detecting Anomalies...")
    
    anomaly_df = detect_anomalies(
        trend_df,
        partition_cols=["source_domain"],
        order_col="dt",
        value_col="article_count",
        window_size=14,
        z_threshold=2.0
    )
    
    print("\n  All anomalies detected:")
    anomaly_df.filter(F.col("is_anomaly")).select(
        "dt", "article_count", "historical_mean", "z_score", "anomaly_type"
    ).show()
    
    # Compute velocity and acceleration
    print("\n[Step 5] Computing Velocity & Acceleration...")
    
    velocity_df = compute_velocity_acceleration(
        anomaly_df,
        order_col="dt",
        value_col="article_count"
    )
    
    velocity_df.select(
        "dt", "article_count", "velocity", "acceleration", "pct_change"
    ).show(15)
    
    # Seasonality analysis
    print("\n[Step 6] Seasonality Analysis...")
    
    seasonal_df = compute_seasonality(velocity_df, "dt", "article_count")
    
    # Average by day of week
    dow_stats = (
        seasonal_df
        .groupBy("day_of_week")
        .agg(
            F.avg("article_count").alias("avg_articles"),
            F.avg("avg_sentiment").alias("avg_sentiment")
        )
        .orderBy("day_of_week")
    )
    
    print("\n  Average by Day of Week (1=Sun, 7=Sat):")
    dow_stats.show()
    
    # Save results
    print("\n[Step 7] Saving Results...")
    
    output_path = "/tmp/output/time_series"
    seasonal_df.write.mode("overwrite").parquet(f"{output_path}/full_analysis")
    dow_stats.write.mode("overwrite").parquet(f"{output_path}/day_of_week_stats")
    
    print("\n" + "=" * 70)
    print("TIME SERIES ANALYSIS COMPLETED")
    print("=" * 70)
    
    spark.stop()


if __name__ == "__main__":
    main()
