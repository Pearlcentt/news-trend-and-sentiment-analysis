from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ArticleRecord:
    article_id: str
    source: str
    source_feed: str
    url: str
    title: str
    summary: str
    body: str
    published_at: int
    fetched_at: int
    ingest_time: int
    language: str
    authors: List[str]
    tags: List[str]
    section: Optional[str]
    category: Optional[str]
    country: Optional[str]
    crawl_status: str
    http_status: int
    content_type: str
    content_length: int
    content_hash_md5: str
    schema_version: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert the record to a JSON-serializable dictionary."""
        return asdict(self)
