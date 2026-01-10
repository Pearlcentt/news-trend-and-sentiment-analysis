#!/bin/bash
# Script to create ConfigMaps for K8s jobs
# This mounts the local project code into K8s for development/testing

NAMESPACE="news-pipeline"

# 1. Create ConfigMap for Spark Jobs (entire jobs/ folder)
# We flatten the structure or recreate it inside the container
# For simplicity, we just tar it or create from files. 
# Kubernetes 'kubectl create configmap --from-file' preserves filenames.

# NOTE: ConfigMaps have a 1MB size limit. For larger codebases, use a PersistentVolume or Docker image.
# Since our scripts are small, ConfigMap is fine for dev.

echo "Creating ConfigMaps in namespace $NAMESPACE..."

# Delete existing
kubectl delete configmap spark-jobs-code -n $NAMESPACE 2>/dev/null
kubectl delete configmap crawler-code -n $NAMESPACE 2>/dev/null
kubectl delete configmap avro-schemas -n $NAMESPACE 2>/dev/null
kubectl delete configmap data-quality-code -n $NAMESPACE 2>/dev/null

# Create spark-jobs-code (Contains jobs/ content)
# We select key files to avoid size limits
kubectl create configmap spark-jobs-code \
    --from-file=../jobs/batch/batch_pipeline.py \
    --from-file=../jobs/streaming/streaming_pipeline.py \
    --from-file=../jobs/streaming/alert_consumer.py \
    --from-file=../jobs/quality/checkpoint_runner.py \
    --from-file=../jobs/analytics/ml_pipeline.py \
    --from-file=../jobs/analytics/time_series.py \
    --from-file=../jobs/analytics/graph_analytics.py \
    --from-file=../jobs/analytics/advanced_aggregations.py \
    --from-file=../jobs/utils/sentiment.py \
    --from-file=../jobs/utils/spark_utils.py \
    --from-file=../jobs/config/rt-config.yaml \
    --from-file=../jobs/config/batch-config.yaml \
    --from-file=../jobs/config/analytics-config.yaml \
    -n $NAMESPACE

# Create crawler-code
kubectl create configmap crawler-code \
    --from-file=../crawler/news_crawler.py \
    --from-file=../crawler/historical_crawler.py \
    --from-file=../crawler/feeds.py \
    -n $NAMESPACE

# Create dashboard-code (NEW: allow hot-reload of app.py)
kubectl delete configmap dashboard-code -n $NAMESPACE 2>/dev/null
kubectl create configmap dashboard-code \
    --from-file=../dashboard/app.py \
    -n $NAMESPACE

# Create avro-schemas
kubectl create configmap avro-schemas \
    --from-file=../schemas/news_raw.avsc \
    --from-file=../schemas/news_processed.avsc \
    -n $NAMESPACE

echo "ConfigMaps created!"
kubectl get configmap -n $NAMESPACE
