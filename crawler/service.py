from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import List, Optional

import requests

from .config import AppConfig, FeedConfig
from .feeds import fetch_article_body, fetch_feed
from .records import ArticleRecord
from .sinks import Sink
from .state import StateStore

LOG = logging.getLogger("crawler.service")


class CrawlerService:
    """Single-run crawler that normalizes feed entries and persists them via a sink."""

    def __init__(self, config: AppConfig, sink: Sink):
        self.config = config
        self.sink = sink
        self.state_store = StateStore(config.crawler.state_store)

    def run_once(self) -> int:
        state = self.state_store.load()
        collected: List[ArticleRecord] = []

        for feed in self.config.feeds:
            last_seen = state.get(feed.name, 0)
            raw_entries = fetch_feed(feed)
            new_entries = [entry for entry in raw_entries if entry["published_ms"] > last_seen]
            if feed.max_articles:
                new_entries = new_entries[: feed.max_articles]
            if self.config.crawler.max_articles_per_feed:
                new_entries = new_entries[: self.config.crawler.max_articles_per_feed]

            if not new_entries:
                LOG.info("No new articles for %s", feed.name)
                continue

            new_entries.sort(key=lambda entry: entry["published_ms"])
            LOG.info("Processing %d articles from %s", len(new_entries), feed.name)
            for article in new_entries:
                record = self._build_record(article, feed)
                if record:
                    collected.append(record)
                # Advance per-feed checkpoint whether or not the article was persisted
                state[feed.name] = max(state.get(feed.name, 0), article["published_ms"])

        if collected:
            self._preview(collected)
            self.sink.write(collected)
            self.state_store.save(state)
        else:
            LOG.info("No records collected this run.")

        return len(collected)

    def _build_record(self, raw_article: dict, feed: FeedConfig) -> Optional[ArticleRecord]:
        attempts = 0
        max_attempts = max(1, self.config.crawler.max_retries)

        while attempts < max_attempts:
            try:
                body_text, crawl_status, http_status, content_type, content_length = self._resolve_body(raw_article)
                now_ms = int(time.time() * 1000)
                content_hash = hashlib.md5(body_text.encode("utf-8")).hexdigest()
                return ArticleRecord(
                    article_id=str(uuid.uuid4()),
                    source=feed.name,
                    source_feed=feed.section or feed.name,
                    url=raw_article.get("link") or "",
                    title=raw_article.get("title", ""),
                    summary=raw_article.get("summary", ""),
                    body=body_text,
                    published_at=raw_article["published_ms"],
                    fetched_at=now_ms,
                    ingest_time=now_ms,
                    language=raw_article.get("language", "en"),
                    authors=raw_article.get("authors", []),
                    tags=raw_article.get("tags", []),
                    section=raw_article.get("section"),
                    category=raw_article.get("category"),
                    country=self.config.crawler.default_country,
                    crawl_status=crawl_status,
                    http_status=http_status,
                    content_type=content_type,
                    content_length=content_length,
                    content_hash_md5=content_hash,
                    schema_version=self.config.crawler.schema_version,
                )
            except requests.RequestException as exc:
                attempts += 1
                LOG.warning(
                    "Request failed for %s (attempt %d/%d): %s",
                    raw_article.get("link"),
                    attempts,
                    max_attempts,
                    exc,
                )
                time.sleep(min(2**attempts, 30))
            except Exception:
                LOG.exception("Unhandled error on article %s", raw_article.get("id"))
                return None

        LOG.error("Giving up on %s after %d attempts", raw_article.get("id"), attempts)
        return None

    def _resolve_body(self, raw_article: dict) -> tuple[str, str, int, str, int]:
        if raw_article.get("summary_only") or not raw_article.get("link"):
            body_text = raw_article.get("summary", "")
            return body_text, "summary_only", 0, "text/plain", len(body_text)

        response = fetch_article_body(raw_article["link"], timeout=self.config.crawler.request_timeout)
        if not response.get("error"):
            return (
                response["body"],
                "ok",
                response["http_status"],
                response["content_type"],
                response["content_length"],
            )

        body_text = raw_article.get("summary", "")
        status = "partial_content" if body_text else "http_error"
        return (
            body_text,
            status,
            response["http_status"],
            response["content_type"],
            response["content_length"],
        )

    def _preview(self, records: List[ArticleRecord]) -> None:
        preview_count = min(self.config.storage.stdout_preview, len(records))
        if preview_count <= 0:
            return
        LOG.info("Previewing first %d records:", preview_count)
        for idx in range(preview_count):
            LOG.info("%d) %s", idx + 1, records[idx].title)
