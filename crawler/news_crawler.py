"""
News crawler service.

Supports two modes:
- STREAM (default): Continuous polling with configurable interval (60s)
- BATCH: Single run, suitable for Airflow/cron scheduled jobs

Continuously pulls RSS/APIs, normalizes articles into the NewsRaw Avro schema,
and pushes the events to Kafka. Designed to run as a long-lived job/container.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
import yaml
from confluent_kafka import KafkaException, Producer

from avro_producer import AvroKafkaProducer
from schema_registry import SchemaRegistry

# Import shared modules instead of duplicating
from config import FeedConfig
from feeds import fetch_feed, fetch_article_body as _fetch_article_body


LOG = logging.getLogger("news_crawler")


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    
    # Override with environment variables (for K8s deployment)
    if os.getenv("KAFKA_BOOTSTRAP_SERVERS"):
        config["kafka"]["bootstrap_servers"] = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if os.getenv("SCHEMA_REGISTRY_URL"):
        config["schema_registry"]["url"] = os.getenv("SCHEMA_REGISTRY_URL")
    if os.getenv("CRAWL_INTERVAL"):
        config["crawler"]["poll_interval_seconds"] = int(os.getenv("CRAWL_INTERVAL"))
    # Security: SSL verification can be disabled for local dev only
    if os.getenv("VERIFY_SSL"):
        config["crawler"]["verify_ssl"] = os.getenv("VERIFY_SSL").lower() == "true"
    # Rate limiting between feed fetches
    if os.getenv("RATE_LIMIT_DELAY"):
        config["crawler"]["rate_limit_delay"] = float(os.getenv("RATE_LIMIT_DELAY"))
    if os.getenv("CRAWLER_STATE_STORE"):
        config["crawler"]["state_store"] = os.getenv("CRAWLER_STATE_STORE")
    
    return config


def load_state(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return {}


def save_state(path: Path, state: Dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    tmp_path.replace(path)


# fetch_rss is now replaced by fetch_feed from feeds.py
# Using a wrapper for backward compatibility
def fetch_rss(feed: FeedConfig):
    """Wrapper around fetch_feed for backward compatibility."""
    for article in fetch_feed(feed):
        yield article
# fetch_article_body is now imported from feeds.py as _fetch_article_body
# Using a wrapper to maintain the same interface with SSL and rate limit support
def fetch_article_body(
    url: str, 
    timeout: int = 10,
    verify_ssl: bool = True,
    rate_limit_delay: float = 0.5
) -> Dict[str, Any]:
    """Wrapper around feeds.fetch_article_body for backward compatibility."""
    return _fetch_article_body(url, timeout, verify_ssl, rate_limit_delay)


def build_event(
    raw_article: Dict[str, Any], crawl_cfg: Dict[str, Any], source_domain: str
) -> Dict[str, Any]:
    # If the feed is marked as summary-only (e.g., paywalled source), avoid HTTP fetches.
    if raw_article.get("summary_only"):
        body_text = raw_article.get("summary", "")
        body_result = {
            "http_status": 0,
            "content_type": "text/plain",
            "content_length": len(body_text),
            "error": False,
        }
        crawl_status = "summary_only"
    else:
        # Get security and rate limit settings from config
        verify_ssl = crawl_cfg.get("verify_ssl", True)
        rate_limit_delay = crawl_cfg.get("rate_limit_delay", 0.5)
        body_result = fetch_article_body(
            raw_article["link"], 
            crawl_cfg["request_timeout"],
            verify_ssl=verify_ssl,
            rate_limit_delay=rate_limit_delay
        )
        body_text = body_result["body"]
        crawl_status = "ok" if not body_result.get("error") else "http_error"

        # Fallback: for paywalled/forbidden responses, use feed summary so we still emit usable content.
        if crawl_status != "ok" and not body_text and raw_article.get("summary"):
            body_text = raw_article["summary"]
            crawl_status = "partial_content"
            LOG.warning(
                "Using RSS summary as body for %s due to HTTP status %s",
                raw_article["id"],
                body_result.get("http_status"),
            )
    normalized_title = raw_article["title"].lower()
    content_hash = hashlib.md5(body_text.encode("utf-8")).hexdigest()
    simhash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:16]

    now_ms = int(time.time() * 1000)
    return {
        "article_id": raw_article["id"],
        "source_domain": source_domain,
        "source_feed": raw_article["section"] or crawl_cfg.get("default_feed_name"),
        "canonical_url": raw_article["link"],
        "published_at": raw_article["published_ms"],
        "updated_at": raw_article["published_ms"],
        "authors": raw_article["authors"],
        "section": raw_article["section"],
        "category": raw_article["category"],
        "tags": raw_article["tags"],
        "title": raw_article["title"],
        "body_text": body_text,
        "language": raw_article["language"],
        "country": crawl_cfg.get("default_country"),
        "images": [],
        "outlinks": [],
        "ingest_time": now_ms,
        "crawl_status": crawl_status,
        "http_status": body_result["http_status"],
        "content_type": body_result["content_type"],
        "content_length": body_result["content_length"],
        "normalized_title": normalized_title,
        "content_hash_md5": content_hash,
        "simhash64": str(int(simhash, 16)),
        "event_time": raw_article["published_ms"],
        "schema_version": crawl_cfg.get("schema_version", 1),
    }


def backoff_sleep(attempt: int, base: float = 1.0, cap: float = 30.0) -> None:
    sleep_for = min(cap, base * (2 ** attempt))
    LOG.info("Backing off for %.1f seconds", sleep_for)
    time.sleep(sleep_for)


def build_producer_config(kafka_cfg: Dict[str, Any]) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "bootstrap.servers": kafka_cfg["bootstrap_servers"],
        "client.id": kafka_cfg.get("client_id", "news-crawler"),
        "enable.idempotence": True,
        "acks": "all",
        "security.protocol": kafka_cfg.get("security_protocol", "PLAINTEXT"),
    }
    sasl_mech = kafka_cfg.get("sasl_mechanisms")
    sasl_user = kafka_cfg.get("sasl_username")
    sasl_pass = kafka_cfg.get("sasl_password")

    # Only set SASL parameters when provided to avoid invalid-null errors.
    if sasl_mech:
        cfg["sasl.mechanisms"] = sasl_mech
    if sasl_user:
        cfg["sasl.username"] = sasl_user
    if sasl_pass:
        cfg["sasl.password"] = sasl_pass
    return cfg


def run(config_path: Path, print_events: bool = False, mode: str = "stream") -> None:
    config = load_yaml(config_path)
    config_dir = config_path.resolve().parent
    kafka_cfg = config["kafka"]
    crawl_cfg = config["crawler"]
    max_retries = crawl_cfg.get("max_retries", 3)
    feeds = [FeedConfig(**entry) for entry in config["feeds"]]
    state_path = Path(crawl_cfg.get("state_store", "./state/crawler_state.json"))
    if not state_path.is_absolute():
        state_path = (config_dir / state_path).resolve()
    state = load_state(state_path)

    producer = Producer(build_producer_config(kafka_cfg))

    schema_path = Path(config["schema_registry"]["schema_path"])
    if not schema_path.is_absolute():
        schema_path = (config_dir / schema_path).resolve()

    schema_registry = SchemaRegistry(config["schema_registry"]["url"])
    avro_producer = AvroKafkaProducer(
        producer=producer,
        schema_registry=schema_registry,
        schema_path=schema_path,
        subject=config["schema_registry"]["subject"],
    )

    poll_interval = crawl_cfg.get("poll_interval_seconds", 60)
    LOG.info("Starting crawler with %d feeds, poll interval %ss", len(feeds), poll_interval)

    while True:
        for feed in feeds:
            last_seen = state.get(feed.name, 0)
            articles = list(fetch_rss(feed))
            new_articles = [a for a in articles if a["published_ms"] > last_seen]
            if not new_articles:
                LOG.debug("No new articles for %s", feed.name)
                continue
            new_articles.sort(key=lambda a: a["published_ms"])
            LOG.info("Found %d new articles on %s", len(new_articles), feed.name)
            for article in new_articles:
                attempts = 0
                while True:
                    try:
                        event = build_event(article, crawl_cfg, source_domain=feed.name)
                        if event["crawl_status"] == "http_error":
                            LOG.warning(
                                "Skipping article %s due to HTTP error status %s",
                                article["id"],
                                event["http_status"],
                            )
                            state[feed.name] = max(
                                state.get(feed.name, 0), article["published_ms"]
                            )
                            break
                        if print_events:
                            preview = event["body_text"][:400]
                            LOG.info(
                                "Event preview | id=%s | title=%s | status=%s | body_len=%d | body_preview=%s",
                                event["article_id"],
                                event["title"],
                                event["crawl_status"],
                                len(event["body_text"]),
                                preview,
                            )
                        avro_producer.send(
                            topic=kafka_cfg["topic"],
                            key=event["article_id"],
                            record=event,
                        )
                        producer.poll(0)
                        state[feed.name] = max(state.get(feed.name, 0), article["published_ms"])
                        break
                    except (requests.RequestException, KafkaException) as exc:
                        LOG.exception("Transient error while processing %s: %s", article["id"], exc)
                        attempts += 1
                        if attempts >= max_retries:
                            LOG.error(
                                "Giving up on %s after %d attempts; advancing state",
                                article["id"],
                                attempts,
                            )
                            state[feed.name] = max(
                                state.get(feed.name, 0), article["published_ms"]
                            )
                            break
                        backoff_sleep(attempts)
                    except Exception:  # pylint: disable=broad-except
                        LOG.exception("Fatal error on article %s", article["id"])
                        state[feed.name] = max(
                            state.get(feed.name, 0), article["published_ms"]
                        )
                        break
        save_state(state_path, state)
        producer.flush()
        
        # BATCH MODE: Single run, then exit (for Airflow/cron scheduling)
        if mode == "batch":
            LOG.info("Batch mode: completed single crawl run, exiting")
            break
        
        # STREAM MODE: Continuous polling (most popular for real-time pipelines)
        LOG.info("Stream mode: sleeping %d seconds before next poll", poll_interval)
        time.sleep(poll_interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="News crawler to Kafka")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.kafka.yaml"),
        help="Path to Kafka-oriented crawler YAML configuration",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Log a preview of each event before sending to Kafka",
    )
    parser.add_argument(
        "--mode",
        choices=["batch", "stream"],
        default="stream",
        help="batch: single run for scheduled jobs; stream: continuous polling (default)",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level)
    run(args.config, print_events=args.print_events, mode=args.mode)

