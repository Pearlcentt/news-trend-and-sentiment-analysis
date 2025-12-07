from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class FeedConfig:
    name: str
    url: str
    section: Optional[str] = None
    category: Optional[str] = None
    language: str = "en"
    summary_only: bool = False
    max_articles: Optional[int] = None


@dataclass
class CrawlerSettings:
    request_timeout: int = 10
    state_store: Path = Path("./state/crawler_state.json")
    default_country: str = "US"
    schema_version: int = 1
    max_retries: int = 2
    max_articles_per_feed: Optional[int] = None


@dataclass
class StorageSettings:
    mode: str = "jsonl"
    output_dir: Path = Path("../../data/raw")
    filename_prefix: str = "news_raw"
    stdout_preview: int = 2


@dataclass
class AppConfig:
    crawler: CrawlerSettings
    feeds: List[FeedConfig]
    storage: StorageSettings


def _resolve(base_dir: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found at {path}")
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base_dir = path.resolve().parent

    crawler_cfg = raw.get("crawler", {})
    storage_cfg = raw.get("storage", {})
    feeds_cfg = raw.get("feeds") or []
    if not feeds_cfg:
        raise ValueError("At least one feed entry is required in the config file.")

    feeds: List[FeedConfig] = []
    for entry in feeds_cfg:
        if "name" not in entry or "url" not in entry:
            raise ValueError(f"Feed entry missing required fields: {entry}")
        feeds.append(
            FeedConfig(
                name=entry["name"],
                url=entry["url"],
                section=entry.get("section"),
                category=entry.get("category"),
                language=entry.get("language", "en"),
                summary_only=entry.get("summary_only", False),
                max_articles=entry.get("max_articles"),
            )
        )

    crawler = CrawlerSettings(
        request_timeout=crawler_cfg.get("request_timeout", 10),
        state_store=_resolve(base_dir, crawler_cfg.get("state_store", "./state/crawler_state.json")),
        default_country=crawler_cfg.get("default_country", "US"),
        schema_version=crawler_cfg.get("schema_version", 1),
        max_retries=crawler_cfg.get("max_retries", 2),
        max_articles_per_feed=crawler_cfg.get("max_articles_per_feed"),
    )

    storage = StorageSettings(
        mode=storage_cfg.get("mode", "jsonl"),
        output_dir=_resolve(base_dir, storage_cfg.get("output_dir", "../../data/raw")),
        filename_prefix=storage_cfg.get("filename_prefix", "news_raw"),
        stdout_preview=storage_cfg.get("stdout_preview", 2),
    )

    return AppConfig(crawler=crawler, feeds=feeds, storage=storage)
