"""
Historical News Data Crawler
Fetches historical news from multiple archive sources:
1. GDELT Project (free global news archive)
2. Wayback Machine (Internet Archive)
3. NewsAPI (if API key provided)

Usage:
    python historical_crawler.py --days 90 --output mongodb
"""
import os
import sys
import json
import hashlib
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, quote
import time

import requests
from bs4 import BeautifulSoup

# Try to import optional dependencies
try:
    from pymongo import MongoClient
    HAS_MONGO = True
except ImportError:
    HAS_MONGO = False

try:
    from confluent_kafka import Producer
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroSerializer
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False

# Configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://mongodb:27017')
KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka-broker:9092')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY', '')
GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


class GDELTCrawler:
    """
    Crawler for GDELT Project v2 API
    GDELT indexes news articles from around the world every 15 minutes
    Free API with historical data back to 2017
    """
    
    def __init__(self):
        self.base_url = GDELT_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'NewsPipelineHistoricalCrawler/1.0'
        })
    
    def search(
        self,
        query: str = "",
        start_date: datetime = None,
        end_date: datetime = None,
        max_records: int = 250,
        source_lang: str = "english"
    ) -> List[Dict[str, Any]]:
        """
        Search GDELT for articles
        
        Args:
            query: Search query (empty for all news)
            start_date: Start date for search
            end_date: End date for search
            max_records: Maximum records to return (max 250 per request)
            source_lang: Language filter
        """
        # Format dates for GDELT
        if start_date:
            start_str = start_date.strftime("%Y%m%d%H%M%S")
        else:
            start_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
        
        if end_date:
            end_str = end_date.strftime("%Y%m%d%H%M%S")
        else:
            end_str = datetime.now().strftime("%Y%m%d%H%M%S")
        
        params = {
            "query": query if query else "",
            "mode": "artlist",
            "maxrecords": str(max_records),
            "format": "json",
            "startdatetime": start_str,
            "enddatetime": end_str,
            "sourcelang": source_lang,
        }
        
        try:
            response = self.session.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            articles = []
            for item in data.get("articles", []):
                article = self._parse_gdelt_article(item)
                if article:
                    articles.append(article)
            
            LOG.info(f"GDELT: Found {len(articles)} articles for {start_date.strftime('%Y-%m-%d') if start_date else 'recent'}")
            return articles
            
        except requests.RequestException as e:
            LOG.error(f"GDELT API error: {e}")
            return []
        except json.JSONDecodeError:
            LOG.error("GDELT returned invalid JSON")
            return []
    
    def _parse_gdelt_article(self, item: Dict) -> Optional[Dict[str, Any]]:
        """Parse GDELT article to our schema"""
        try:
            url = item.get("url", "")
            domain = urlparse(url).netloc.replace("www.", "")
            
            # Parse date
            date_str = item.get("seendate", "")
            if date_str:
                try:
                    event_time = datetime.strptime(date_str, "%Y%m%dT%H%M%SZ")
                except ValueError:
                    event_time = datetime.now()
            else:
                event_time = datetime.now()
            
            title = item.get("title", "")
            if not title:
                return None
            
            article = {
                "article_id": f"gdelt_{hashlib.md5(url.encode()).hexdigest()[:16]}",
                "source_domain": domain,
                "title": title,
                "body_text": item.get("socialimage", ""),  # GDELT doesn't provide full text
                "url": url,
                "published_at": int(event_time.timestamp() * 1000),
                "event_time": int(event_time.timestamp() * 1000),
                "ingest_time": int(datetime.now().timestamp() * 1000),
                "language": item.get("language", "English"),
                "section": item.get("domain", "general"),
                "tags": [],
                "content_hash_md5": hashlib.md5(title.encode()).hexdigest(),
                "source": "gdelt",
            }
            return article
        except Exception as e:
            LOG.warning(f"Error parsing GDELT article: {e}")
            return None
    
    def crawl_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        query: str = "",
        articles_per_day: int = 100
    ) -> List[Dict[str, Any]]:
        """Crawl articles for a date range"""
        all_articles = []
        current_date = start_date
        
        while current_date <= end_date:
            next_date = current_date + timedelta(days=1)
            
            # Search for this day
            articles = self.search(
                query=query,
                start_date=current_date,
                end_date=next_date,
                max_records=min(articles_per_day, 250)
            )
            all_articles.extend(articles)
            
            LOG.info(f"Date {current_date.strftime('%Y-%m-%d')}: {len(articles)} articles (total: {len(all_articles)})")
            
            current_date = next_date
            time.sleep(0.5)  # Rate limiting
        
        return all_articles


class WaybackCrawler:
    """
    Crawler for Internet Archive Wayback Machine
    Retrieves archived versions of news pages
    """
    
    def __init__(self):
        self.cdx_url = "https://web.archive.org/cdx/search/cdx"
        self.session = requests.Session()
    
    def search_archives(
        self,
        domain: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search Wayback Machine for archived pages from a domain"""
        
        params = {
            "url": f"{domain}/*",
            "matchType": "prefix",
            "from": start_date.strftime("%Y%m%d"),
            "to": end_date.strftime("%Y%m%d"),
            "output": "json",
            "limit": str(limit),
            # Fixed: Use list for multiple filter values (was overwriting)
            "filter": ["statuscode:200", "mimetype:text/html"],
        }
        
        try:
            response = self.session.get(self.cdx_url, params=params, timeout=30)
            response.raise_for_status()
            
            lines = response.text.strip().split('\n')
            if len(lines) <= 1:
                return []
            
            # Parse CDX format
            articles = []
            for line in lines[1:]:  # Skip header
                parts = line.strip().split(' ')
                if len(parts) >= 7:
                    timestamp, original_url = parts[1], parts[2]
                    
                    article = {
                        "article_id": f"wayback_{hashlib.md5(original_url.encode()).hexdigest()[:16]}",
                        "source_domain": domain,
                        "url": original_url,
                        "wayback_url": f"https://web.archive.org/web/{timestamp}/{original_url}",
                        "archived_at": timestamp,
                        "source": "wayback",
                    }
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            LOG.error(f"Wayback API error: {e}")
            return []


class NewsAPICrawler:
    """
    Crawler for NewsAPI (requires API key)
    Free tier: 100 requests/day, 1 month history
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2/everything"
    
    def search(
        self,
        query: str,
        start_date: datetime,
        end_date: datetime,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """Search NewsAPI for articles"""
        if not self.api_key:
            LOG.warning("NewsAPI key not provided")
            return []
        
        params = {
            "q": query or "news",
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": self.api_key,
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            articles = []
            for item in data.get("articles", []):
                article = self._parse_newsapi_article(item)
                if article:
                    articles.append(article)
            
            return articles
            
        except Exception as e:
            LOG.error(f"NewsAPI error: {e}")
            return []
    
    def _parse_newsapi_article(self, item: Dict) -> Optional[Dict[str, Any]]:
        """Parse NewsAPI article to our schema"""
        try:
            url = item.get("url", "")
            domain = urlparse(url).netloc.replace("www.", "")
            
            published_at = item.get("publishedAt", "")
            if published_at:
                event_time = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            else:
                event_time = datetime.now()
            
            title = item.get("title", "")
            content = item.get("content", "") or item.get("description", "")
            
            return {
                "article_id": f"newsapi_{hashlib.md5(url.encode()).hexdigest()[:16]}",
                "source_domain": domain,
                "title": title,
                "body_text": content,
                "url": url,
                "published_at": int(event_time.timestamp() * 1000),
                "event_time": int(event_time.timestamp() * 1000),
                "ingest_time": int(datetime.now().timestamp() * 1000),
                "language": "en",
                "section": "general",
                "tags": [],
                "content_hash_md5": hashlib.md5(content.encode()).hexdigest(),
                "source": "newsapi",
                "author": item.get("author"),
            }
        except Exception as e:
            LOG.warning(f"Error parsing NewsAPI article: {e}")
            return None


class HistoricalDataStorage:
    """Storage handler for historical articles"""
    
    def __init__(self, output_type: str = "mongodb"):
        self.output_type = output_type
        self.mongo_client = None
        
        if output_type == "mongodb" and HAS_MONGO:
            try:
                self.mongo_client = MongoClient(MONGODB_URI)
                LOG.info(f"Connected to MongoDB: {MONGODB_URI}")
            except Exception as e:
                LOG.error(f"MongoDB connection failed: {e}")
    
    def store(self, articles: List[Dict[str, Any]]):
        """Store articles to configured backend"""
        if not articles:
            LOG.warning("No articles to store")
            return
        
        if self.output_type == "mongodb" and self.mongo_client:
            self._store_mongodb(articles)
        elif self.output_type == "json":
            self._store_json(articles)
        else:
            LOG.warning(f"Unknown output type: {self.output_type}")
    
    def _store_mongodb(self, articles: List[Dict[str, Any]]):
        """Store to MongoDB"""
        try:
            db = self.mongo_client["news_analytics"]
            
            # Insert articles using bulk operations for efficiency
            if articles:
                from pymongo import UpdateOne
                # Build bulk operations (single DB round-trip instead of N)
                operations = [
                    UpdateOne(
                        {"article_id": article["article_id"]},
                        {"$set": article},
                        upsert=True
                    )
                    for article in articles
                ]
                result = db.historical_articles.bulk_write(operations, ordered=False)
                LOG.info(f"Stored {result.upserted_count + result.modified_count} articles to MongoDB (bulk)")
            
            # Update stats
            self._update_stats(db)
            
            # Also update news_rt for dashboard
            self._update_realtime_db(articles)
            
        except Exception as e:
            LOG.error(f"MongoDB storage error: {e}")
    
    def _update_stats(self, db):
        """Compute and store aggregated statistics"""
        # Source stats
        pipeline = [
            {"$group": {
                "_id": "$source_domain",
                "article_count": {"$sum": 1},
                "sources": {"$addToSet": "$source"},
            }}
        ]
        stats = list(db.historical_articles.aggregate(pipeline))
        
        for s in stats:
            db.source_stats.update_one(
                {"source_domain": s["_id"]},
                {"$set": {
                    "article_count": s["article_count"],
                    "updated_at": datetime.now()
                }},
                upsert=True
            )
        
        LOG.info(f"Updated statistics for {len(stats)} sources")
    
    def _update_realtime_db(self, articles: List[Dict[str, Any]]):
        """Update news_rt database for Streamlit dashboard"""
        try:
            db_rt = self.mongo_client["news_rt"]
            
            # Add recent articles to processed_news
            recent = articles[-100:] if len(articles) > 100 else articles
            for a in recent:
                db_rt.processed_news.update_one(
                    {"article_id": a["article_id"]},
                    {"$set": {
                        "source_domain": a.get("source_domain", "unknown"),
                        "title": a.get("title", ""),
                        "sentiment": self._simple_sentiment(a.get("title", "")),
                        "process_time": datetime.now()
                    }},
                    upsert=True
                )
            
            # Update rt_trends
            sources = {}
            for a in articles:
                domain = a.get("source_domain", "unknown")
                if domain not in sources:
                    sources[domain] = {"count": 0, "positive": 0, "negative": 0}
                sources[domain]["count"] += 1
                
                sentiment = self._simple_sentiment(a.get("title", ""))
                if sentiment == "positive":
                    sources[domain]["positive"] += 1
                elif sentiment == "negative":
                    sources[domain]["negative"] += 1
            
            for domain, stats in sources.items():
                db_rt.rt_trends.update_one(
                    {"source_domain": domain},
                    {"$inc": {
                        "article_count": stats["count"],
                        "positive_count": stats["positive"],
                        "negative_count": stats["negative"],
                    },
                    "$set": {"updated_at": datetime.now()}},
                    upsert=True
                )
            
        except Exception as e:
            LOG.error(f"Error updating realtime db: {e}")
    
    def _simple_sentiment(self, text: str) -> str:
        """Simple sentiment analysis using shared module."""
        # Import from unified sentiment module for consistency
        try:
            import sys
            from pathlib import Path
            # Add jobs directory to path
            jobs_path = Path(__file__).parent.parent / "jobs"
            if str(jobs_path) not in sys.path:
                sys.path.insert(0, str(jobs_path))
            from utils.sentiment import simple_sentiment_label
            return simple_sentiment_label(text)
        except ImportError:
            # Fallback if jobs module not available (standalone crawler)
            if not text:
                return "neutral"
            text_lower = text.lower()
            pos = sum(1 for w in ["surge", "rise", "gain", "growth", "success", "profit", "win", "positive"] if w in text_lower)
            neg = sum(1 for w in ["fall", "drop", "decline", "crash", "crisis", "loss", "fail", "negative"] if w in text_lower)
            return "positive" if pos > neg else "negative" if neg > pos else "neutral"
    
    def _store_json(self, articles: List[Dict[str, Any]]):
        """Store to JSON file"""
        output_file = f"historical_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(articles, f, indent=2, default=str)
        LOG.info(f"Stored {len(articles)} articles to {output_file}")
    
    def close(self):
        if self.mongo_client:
            self.mongo_client.close()


def main():
    parser = argparse.ArgumentParser(description="Historical News Crawler")
    parser.add_argument("--days", type=int, default=90, help="Number of days to crawl back")
    parser.add_argument("--per-day", type=int, default=100, help="Articles per day (max 250)")
    parser.add_argument("--output", choices=["mongodb", "json"], default="mongodb", help="Output destination")
    parser.add_argument("--query", type=str, default="", help="Search query")
    args = parser.parse_args()
    
    print("=" * 60)
    print("HISTORICAL NEWS CRAWLER")
    print(f"Date range: {args.days} days back")
    print(f"Output: {args.output}")
    print("=" * 60)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    
    all_articles = []
    
    # 1. Crawl from GDELT (primary source)
    print("\n[1/3] Crawling GDELT Project...")
    gdelt = GDELTCrawler()
    gdelt_articles = gdelt.crawl_date_range(
        start_date=start_date,
        end_date=end_date,
        query=args.query,
        articles_per_day=min(args.per_day, 250)
    )
    all_articles.extend(gdelt_articles)
    print(f"  GDELT: {len(gdelt_articles)} articles")
    
    # 2. Crawl from NewsAPI (if key available)
    if NEWSAPI_KEY:
        print("\n[2/3] Crawling NewsAPI...")
        newsapi = NewsAPICrawler(NEWSAPI_KEY)
        # NewsAPI limits to 1 month for free tier
        newsapi_start = max(start_date, datetime.now() - timedelta(days=30))
        newsapi_articles = newsapi.search(
            query=args.query or "technology OR business OR politics",
            start_date=newsapi_start,
            end_date=end_date
        )
        all_articles.extend(newsapi_articles)
        print(f"  NewsAPI: {len(newsapi_articles)} articles")
    else:
        print("\n[2/3] NewsAPI: Skipped (no API key)")
    
    # 3. No Wayback crawling (too slow for bulk data)
    print("\n[3/3] Wayback Machine: Skipped (individual article fetch only)")
    
    # Remove duplicates by article_id
    seen = set()
    unique_articles = []
    for a in all_articles:
        if a["article_id"] not in seen:
            seen.add(a["article_id"])
            unique_articles.append(a)
    
    print(f"\nTotal unique articles: {len(unique_articles)}")
    
    # Store results
    print("\nStoring articles...")
    storage = HistoricalDataStorage(args.output)
    storage.store(unique_articles)
    storage.close()
    
    print("\n" + "=" * 60)
    print("HISTORICAL CRAWL COMPLETE")
    print(f"Total articles: {len(unique_articles)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
