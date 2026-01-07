#!/bin/bash
# deploy.sh - Deploy News Pipeline to Kubernetes

set -e

echo "=========================================="
echo "  News Trend & Sentiment Analysis"
echo "  Kubernetes Deployment Script"
echo "=========================================="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl is not installed"
    exit 1
fi

# Deploy in order
echo ""
echo "[1/12] Creating namespace and PVCs..."
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/11-persistent-volumes.yaml

echo ""
echo "[2/12] Deploying Kafka & Schema Registry..."
kubectl apply -f k8s/01-kafka.yaml

echo ""
echo "[3/12] Deploying MongoDB..."
kubectl apply -f k8s/02-mongodb.yaml

echo ""
echo "[4/12] Deploying Spark cluster..."
kubectl apply -f k8s/03-spark.yaml

echo ""
echo "[5/12] Deploying Trino..."
kubectl apply -f k8s/04-trino.yaml

echo ""
echo "[6/12] Deploying Grafana..."
kubectl apply -f k8s/05-grafana.yaml

echo ""
echo "[7/12] Deploying News Crawler..."
kubectl apply -f k8s/06-crawler.yaml

echo ""
echo "[8/12] Deploying HDFS..."
kubectl apply -f k8s/07-hdfs.yaml || echo "HDFS deployment skipped (may need PV support)"

echo ""
echo "[9/12] Deploying Cassandra..."
kubectl apply -f k8s/08-cassandra.yaml || echo "Cassandra deployment skipped (may need PV support)"

echo ""
echo "[10/12] Deploying Streamlit Dashboard..."
kubectl apply -f k8s/09-streamlit.yaml

echo ""
echo "[11/12] Deploying Airflow..."
kubectl apply -f k8s/10-airflow.yaml

echo ""
echo "[12/13] Deploying Spark Streaming Job..."
kubectl apply -f k8s/12-spark-streaming-job.yaml

echo ""
echo "[13/13] Deploying Spark Batch CronJob..."
kubectl apply -f k8s/13-spark-batch-cronjob.yaml

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "Wait for pods to be ready:"
echo "  kubectl get pods -n news-pipeline -w"
echo ""
echo "Access services:"
echo "  Streamlit: kubectl port-forward svc/streamlit-dashboard 8501:8501 -n news-pipeline"
echo "  Grafana:   kubectl port-forward svc/grafana 3000:3000 -n news-pipeline"
echo "  Airflow:   kubectl port-forward svc/airflow 8080:8080 -n news-pipeline"
echo "  Trino:     kubectl port-forward svc/trino 8085:8080 -n news-pipeline"
echo "  Spark UI:  kubectl port-forward svc/spark-master 8090:8080 -n news-pipeline"
echo ""
echo "Check streaming job logs:"
echo "  kubectl logs -f deployment/spark-streaming-job -n news-pipeline"
echo ""

