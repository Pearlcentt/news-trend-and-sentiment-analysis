from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from .config import FeedConfig

LOG = logging.getLogger("crawler.feeds")


def fetch_feed(feed: FeedConfig) -> List[Dict[str, Any]]:
    """Pull RSS/Atom feed entries."""
    parsed = feedparser.parse(feed.url)
    articles: List[Dict[str, Any]] = []
    for entry in parsed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_ms = (
            int(time.mktime(published) * 1000) if published else int(time.time() * 1000)
        )
        articles.append(
            {
                "id": entry.get("id") or entry.get("guid") or str(uuid.uuid4()),
                "title": entry.get("title", "").strip(),
                "summary": entry.get("summary", "").strip(),
                "link": entry.get("link"),
                "tags": [getattr(tag, "term", None) for tag in entry.get("tags", []) if getattr(tag, "term", None)],
                "authors": [getattr(author, "name", None) for author in entry.get("authors", []) if getattr(author, "name", None)]
                if entry.get("authors")
                else [],
                "published_ms": published_ms,
                "section": feed.section,
                "category": feed.category or entry.get("category"),
                "language": feed.language,
                "summary_only": feed.summary_only,
            }
        )
    return articles


def _extract_main_text(soup: BeautifulSoup) -> str:
    """Heuristic extraction of article text from common containers."""
    candidates: List[Optional[BeautifulSoup]] = []
    candidates.append(soup.find("article"))
    candidates.append(soup.find("main"))
    candidates.append(soup.body)
    seen = set()
    texts: List[str] = []

    def collect(node) -> str:
        if node is None:
            return ""
        chunks: List[str] = []
        for tag in node.find_all(["p", "h2", "h3", "li"]):
            text = tag.get_text(" ", strip=True)
            if text:
                chunks.append(text)
        return " ".join(chunks).strip()

    for node in candidates:
        if node and id(node) not in seen:
            seen.add(id(node))
            candidate_text = collect(node)
            if candidate_text:
                texts.append(candidate_text)
    if texts:
        # Prefer the longest block; tends to be the main content.
        return max(texts, key=len)

    # Fallback: all paragraphs in document.
    return " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p")).strip()


def fetch_article_body(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch article body text; return minimal metadata on HTTP failures."""
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsCrawler/1.0; +https://example.com/bot)",
            "Accept-Language": "en-US,en;q=0.8",
        },
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return {
            "body": "",
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type", "text/html"),
            "content_length": int(response.headers.get("Content-Length", len(response.content))),
            "error": True,
        }
    soup = BeautifulSoup(response.text, "html.parser")
    normalized_text = _extract_main_text(soup)
    return {
        "body": normalized_text,
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", "text/html"),
        "content_length": int(response.headers.get("Content-Length", len(response.content))),
        "error": False,
    }
