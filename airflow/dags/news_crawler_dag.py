"""
News Crawler DAG - Airflow Scheduler for Daily News Crawling

This DAG triggers the Kubernetes jobs for:
1. Fresh RSS news crawling
2. Sentiment/Category processing
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.kubernetes_pod import KubernetesPodOperator
from airflow.operators.bash import BashOperator

default_args = {
    'owner': 'news-pipeline',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Daily News Crawler DAG
with DAG(
    'news_crawler_daily',
    default_args=default_args,
    description='Daily news crawling and processing pipeline',
    schedule_interval='0 6 * * *',  # Run daily at 6 AM
    catchup=False,
    tags=['news', 'crawler'],
) as dag:

    # Task 1: Run Fresh RSS Crawler
    crawl_news = BashOperator(
        task_id='crawl_fresh_news',
        bash_command='''
            kubectl delete job -n news-pipeline fresh-news-crawler --ignore-not-found && \
            kubectl apply -f /opt/airflow/k8s/14-fresh-crawler-job.yaml && \
            kubectl wait --for=condition=complete job/fresh-news-crawler -n news-pipeline --timeout=600s
        ''',
    )

    # Task 2: Process Sentiment
    process_sentiment = BashOperator(
        task_id='process_sentiment',
        bash_command='''
            kubectl delete job -n news-pipeline process-historical-data --ignore-not-found && \
            kubectl apply -f /opt/airflow/k8s/15-process-historical-job.yaml && \
            kubectl wait --for=condition=complete job/process-historical-data -n news-pipeline --timeout=300s
        ''',
    )

    # Task 3: Classify Articles
    classify_articles = BashOperator(
        task_id='classify_articles',
        bash_command='''
            kubectl delete job -n news-pipeline classify-articles --ignore-not-found && \
            kubectl apply -f /opt/airflow/k8s/16-classify-articles-job.yaml && \
            kubectl wait --for=condition=complete job/classify-articles -n news-pipeline --timeout=300s
        ''',
    )

    # Task dependencies
    crawl_news >> process_sentiment >> classify_articles
