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
    k8s.V1EnvVar(name='SCHEMA_REGISTRY_URL', value='http://sr-service:8081'),
    k8s.V1EnvVar(name='CRAWLER_STATE_STORE', value='/tmp/crawler_state.json'),
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
            pip install pyyaml requests beautifulsoup4 pymongo feedparser fastavro confluent-kafka --quiet
            export PYTHONPATH="/app/crawler"
            # Task 1: Run Fresh RSS Crawler (in batch mode)
            # Fetch content, push to Kafka, then exit
            python3 /app/crawler/news_crawler.py --mode batch --config /app/crawler/feeds_extended.yaml
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
        image='apache/spark:3.5.0-python3',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pyyaml --target=/tmp/pylibs --quiet 2>/dev/null || true
            export PYTHONPATH="${PYTHONPATH}:/tmp/pylibs:/opt/jobs"
            export HOME=/tmp
            mkdir -p /tmp/.ivy2
            
            /opt/spark/bin/spark-submit \
                --master local[2] \
                --packages org.mongodb.spark:mongo-spark-connector_2.12:10.4.0,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.spark:spark-avro_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
                --conf spark.mongodb.input.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                --conf spark.mongodb.output.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                --conf spark.mongodb.output.database=news_analytics \
                --conf spark.mongodb.output.collection=historical_articles \
                --conf spark.jars.ivy=/tmp/.ivy2 \
                --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
                --conf spark.hadoop.fs.s3a.access.key=minio-admin \
                --conf spark.hadoop.fs.s3a.secret.key=minio-secret-key \
                --conf spark.hadoop.fs.s3a.path.style.access=true \
                --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
                --conf spark.hadoop.fs.s3a.committer.name=directory \
                --conf spark.hadoop.fs.s3a.committer.staging.tmp.path=/tmp/staging \
                --conf spark.hadoop.fs.s3a.fast.upload=true \
                --conf spark.hadoop.fs.s3a.connection.establish.timeout=5000 \
                /opt/jobs/batch_pipeline.py \
                --config /opt/jobs/batch-config.yaml \
                --mode k8s
            '''
        ],
        volumes=[jobs_code_volume, schemas_volume],
        volume_mounts=[jobs_code_mount, schemas_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "1Gi", "cpu": "1"},
            requests={"memory": "512Mi", "cpu": "250m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 3: Classify Articles
    # Task 3: Classify Articles (Train/Update Sentiment Model)
    classify_articles = KubernetesPodOperator(
        task_id='classify_articles',
        name='classify-articles',
        namespace='news-pipeline',
        image='apache/spark:3.5.0-python3',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pyyaml numpy --target=/tmp/pylibs --quiet 2>/dev/null || true
            export PYTHONPATH="${PYTHONPATH}:/tmp/pylibs:/opt/jobs"
            export HOME=/tmp
            mkdir -p /tmp/.ivy2

            /opt/spark/bin/spark-submit \
                --master local[2] \
                --packages org.mongodb.spark:mongo-spark-connector_2.12:10.4.0,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.spark:spark-avro_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
                --conf spark.mongodb.input.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                --conf spark.mongodb.output.uri=mongodb://mongodb:27017/news_analytics.historical_articles \
                --conf spark.mongodb.output.database=news_analytics \
                --conf spark.mongodb.output.collection=historical_articles \
                --conf spark.jars.ivy=/tmp/.ivy2 \
                --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
                --conf spark.hadoop.fs.s3a.access.key=minio-admin \
                --conf spark.hadoop.fs.s3a.secret.key=minio-secret-key \
                --conf spark.hadoop.fs.s3a.path.style.access=true \
                --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
                --conf spark.hadoop.fs.s3a.committer.name=directory \
                --conf spark.hadoop.fs.s3a.committer.staging.tmp.path=/tmp/staging \
                --conf spark.hadoop.fs.s3a.fast.upload=true \
                --conf spark.hadoop.fs.s3a.connection.establish.timeout=5000 \
                /opt/jobs/ml_pipeline.py \
                --config /opt/jobs/analytics-config.yaml
            '''
        ],
        volumes=[jobs_code_volume, schemas_volume],
        volume_mounts=[jobs_code_mount, schemas_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "2Gi", "cpu": "1"},
            requests={"memory": "512Mi", "cpu": "250m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 4: Integrated Analytics
    integrated_analytics = KubernetesPodOperator(
        task_id='integrated_analytics',
        name='integrated-analytics',
        namespace='news-pipeline',
        image='apache/spark:3.5.0-python3',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pyyaml numpy pandas pyarrow --target=/tmp/pylibs --quiet
            export PYTHONPATH="${PYTHONPATH}:/tmp/pylibs:/opt/jobs"
            export HOME=/tmp
            mkdir -p /tmp/.ivy2

            /opt/spark/bin/spark-submit \
                --master local[2] \
                --packages org.mongodb.spark:mongo-spark-connector_2.12:10.4.0,org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.spark:spark-avro_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
                --conf spark.mongodb.input.uri=mongodb://mongodb:27017/news_analytics.processed_articles \
                --conf spark.mongodb.output.uri=mongodb://mongodb:27017/news_analytics.aggregations \
                --conf spark.mongodb.output.database=news_analytics \
                --conf spark.mongodb.output.collection=aggregations \
                --conf spark.jars.ivy=/tmp/.ivy2 \
                --conf spark.hadoop.fs.s3a.endpoint=http://minio:9000 \
                --conf spark.hadoop.fs.s3a.access.key=minio-admin \
                --conf spark.hadoop.fs.s3a.secret.key=minio-secret-key \
                --conf spark.hadoop.fs.s3a.path.style.access=true \
                --conf spark.hadoop.fs.s3a.impl=org.apache.hadoop.fs.s3a.S3AFileSystem \
                --conf spark.hadoop.fs.s3a.committer.name=directory \
                --conf spark.hadoop.fs.s3a.committer.staging.tmp.path=/tmp/staging \
                --conf spark.hadoop.fs.s3a.fast.upload=true \
                --conf spark.hadoop.fs.s3a.connection.establish.timeout=5000 \
                /opt/jobs/advanced_aggregations.py \
                --config /opt/jobs/analytics-config.yaml
            '''
        ],
        volumes=[jobs_code_volume],
        volume_mounts=[jobs_code_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "4Gi", "cpu": "2"},
            requests={"memory": "2Gi", "cpu": "1"}
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

client.close()
            "
            '''
        ],
        env_vars=common_env,
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task 6: Data Quality Validation (Great Expectations)
    validate_data = KubernetesPodOperator(
        task_id='validate_data',
        name='data-quality-check',
        namespace='news-pipeline',
        image='python:3.11-slim',
        cmds=["/bin/bash", "-c"],
        arguments=[
            '''
            pip install pymongo pandas --quiet
            export PYTHONPATH="/opt/jobs"
            # CD to jobs dir (files are flattened)
            cd /opt/jobs
            python3 checkpoint_runner.py
            '''
        ],
        volumes=[jobs_code_volume],
        volume_mounts=[jobs_code_mount],
        env_vars=common_env,
        container_resources=k8s.V1ResourceRequirements(
            limits={"memory": "512Mi", "cpu": "500m"},
            requests={"memory": "256Mi", "cpu": "250m"}
        ),
        get_logs=True,
        is_delete_operator_pod=True,
    )

    # Task dependencies
    crawl_news >> process_sentiment >> validate_data >> classify_articles >> integrated_analytics >> cleanup_rt_data
