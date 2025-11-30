-- Hive schema definitions for batch layer tables
-- These tables point to Parquet files in HDFS

CREATE DATABASE IF NOT EXISTS news_batch;

-- Enriched articles table (partitioned by dt and language)
CREATE TABLE IF NOT EXISTS news_batch.articles_enriched_parquet (
    article_id string,
    source_domain string,
    published_at timestamp,
    language string,
    dedup_group_id string,
    sentiment struct<label: string, polarity: double>,
    entities array<struct<type: string, text: string, norm: string>>,
    keywords array<struct<term: string, score: double>>,
    topics array<struct<topic_id: int, score: double>>,
    embedding_vector_path string,
    model_version string,
    preprocess_version string,
    title string,
    body_text string,
    country string,
    tags array<string>
)
PARTITIONED BY (dt string, language string)
STORED AS PARQUET
LOCATION 'hdfs://namenode:9000/data/news/articles_enriched'
TBLPROPERTIES (
    'parquet.compression'='SNAPPY',
    'projection.enabled'='true',
    'projection.dt.type'='date',
    'projection.dt.format'='yyyy-MM-dd',
    'projection.dt.range'='2025-01-01,2026-12-31',
    'projection.language.type'='enum',
    'projection.language.values'='en,es,fr,de,it,pt,zh,ja,ko,ar'
);

-- Add partitions (example for one day)
-- ALTER TABLE news_batch.articles_enriched_parquet ADD IF NOT EXISTS
-- PARTITION (dt='2025-10-27', language='en')
-- LOCATION 'hdfs://namenode:9000/data/news/articles_enriched/dt=2025-10-27/language=en';

