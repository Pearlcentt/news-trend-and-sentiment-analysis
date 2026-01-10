from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from kubernetes.client import models as k8s

default_args = {
    'owner': 'news-pipeline',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Volume Definitions (Equivalent to K8s YAML volumes)
# 1. Crawler Code ConfigMap
crawler_code_volume = k8s.V1Volume(
    name='crawler-code',
    config_map=k8s.V1ConfigMapVolumeSource(name='crawler-code')
)
# 2. Avro Schemas ConfigMap
schemas_volume = k8s.V1Volume(
    name='schemas',
    config_map=k8s.V1ConfigMapVolumeSource(name='avro-schemas')
)
# 3. Jobs/Spark Code ConfigMap
jobs_code_volume = k8s.V1Volume(
    name='jobs-code',
    config_map=k8s.V1ConfigMapVolumeSource(name='spark-jobs-code')
)

# Volume Mounts
crawler_code_mount = k8s.V1VolumeMount(name='crawler-code', mount_path='/app/crawler')
schemas_mount = k8s.V1VolumeMount(name='schemas', mount_path='/app/schemas')
jobs_code_mount = k8s.V1VolumeMount(name='jobs-code', mount_path='/opt/jobs')

# Env Vars
common_env = [
    k8s.V1EnvVar(name='MONGODB_URI', value='mongodb://mongodb:27017'),
    k8s.V1EnvVar(name='KAFKA_BOOTSTRAP_SERVERS', value='kafka-broker:9092'),
]

# Daily News Crawler DAG
with DAG(
    'news_crawler_daily',
    default_args=default_args,
    description='Daily news crawling and processing pipeline',
    schedule_interval='0 18 * * *',  # Run daily at 6 PM
    catchup=False,
    tags=['news', 'crawler'],
) as dag:

    # Task 1: Run Fresh RSS Crawler
    crawl_news = KubernetesPodOperator(
        task_id='crawl_fresh_news',
        name='fresh-news-crawler',
        namespace='news-pipeline',
        image='python:3.11-slim',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install requests beautifulsoup4 pymongo feedparser --quiet
            export PYTHONPATH="/app"
            # Task 1: Run Fresh RSS Crawler (in batch mode)
            # Fetch content, push to Kafka, then exit
            python3 /app/crawler/news_crawler.py --mode batch
            '''
        ],
        volumes=[crawler_code_volume, schemas_volume],
        volume_mounts=[crawler_code_mount, schemas_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "512Mi", "cpu": "500m"},
            requests={"memory": "256Mi", "cpu": "250m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,  # Clean up pod after completion
    )

    # Task 2: Process Sentiment (Spark)
    process_sentiment = KubernetesPodOperator(
        task_id='process_sentiment',
        name='process-historical-data',
        namespace='news-pipeline',
        image='bitnami/spark:3.5.3',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pyyaml --quiet
            export PYTHONPATH="/opt/jobs"
            spark-submit \
                --master local[2] \
                --packages org.mongodb.spark:mongo-spark-connector_2.12:10.2.0 \
                --conf spark.mongodb.input.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                --conf spark.mongodb.output.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                /opt/jobs/batch/batch_pipeline.py \
                --config /opt/jobs/config/batch-config.yaml \
                --mode k8s
            '''
        ],
        volumes=[jobs_code_volume],
        volume_mounts=[jobs_code_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "1Gi", "cpu": "1"},
            requests={"memory": "512Mi", "cpu": "250m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 3: Classify Articles
    classify_articles = KubernetesPodOperator(
        task_id='classify_articles',
        name='classify-articles',
        namespace='news-pipeline',
        image='python:3.11-slim',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo --quiet
            export PYTHONPATH="/opt/jobs"
            python3 /opt/jobs/analytics/ml_pipeline.py --task classify
            '''
        ],
        volumes=[jobs_code_volume],
        volume_mounts=[jobs_code_mount],
        env_vars=common_env,
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 4: Integrated Analytics
    integrated_analytics = KubernetesPodOperator(
        task_id='integrated_analytics',
        name='integrated-analytics',
        namespace='news-pipeline',
        image='bitnami/spark:3.5.3',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pyyaml pandas pyarrow --quiet
            export PYTHONPATH="/opt/jobs"
            spark-submit \
                --master local[2] \
                --packages org.mongodb.spark:mongo-spark-connector_2.12:10.2.0,graphframes:graphframes:0.8.3-spark3.5-s_2.12 \
                --conf spark.mongodb.input.uri=mongodb://mongodb:27017/news_analytics.processed_articles \
                --conf spark.mongodb.output.uri=mongodb://mongodb:27017/news_analytics.aggregations \
                /opt/jobs/analytics/advanced_aggregations.py \
                --config /opt/jobs/config/analytics-config.yaml
            '''
        ],
        volumes=[jobs_code_volume],
        volume_mounts=[jobs_code_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "2Gi", "cpu": "1"},
            requests={"memory": "1Gi", "cpu": "500m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 5: Cleanup Old Real-Time Data (Lambda Architecture Lifecycle)
    cleanup_rt_data = KubernetesPodOperator(
        task_id='cleanup_rt_data',
        name='cleanup-rt-data',
        namespace='news-pipeline',
        image='python:3.11-slim',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo --quiet
            python3 -c "
from pymongo import MongoClient
from datetime import datetime, timedelta
import os

print('Starting RT Data Cleanup...')
client = MongoClient('mongodb://mongodb:27017')
db = client['news_rt']
# Use string comparison for processed_at format YYYY-MM-DD HH:MM:SS
cutoff = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')

print(f'Deleting records processed before {cutoff}...')
result = db['processed_news'].delete_many({'processed_at': {'$lt': cutoff}})
print(f'✅ Deleted {result.deleted_count} old RT records')

# Also cleanup aggregation collections based on _last_upsert if possible, or just keep them (they are small)
client.close()
            "
            '''
        ],
        env_vars=common_env,
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task dependencies
    crawl_news >> process_sentiment >> classify_articles >> integrated_analytics >> cleanup_rt_data
