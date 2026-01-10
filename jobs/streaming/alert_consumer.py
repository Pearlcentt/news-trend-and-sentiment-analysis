"""
Real-time Alert Consumer

Monitors news pipeline for:
- Breaking news (high article velocity)
- Sentiment spikes (sudden negative surge)
- Data quality failures

Alerts are logged to console and stored in MongoDB.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
import time
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger("AlertConsumer")


class AlertType:
    """Alert type constants"""
    BREAKING_NEWS = "breaking_news"
    SENTIMENT_SPIKE = "sentiment_spike"
    DATA_QUALITY = "data_quality"
    SOURCE_DOWN = "source_down"
    HIGH_VOLUME = "high_volume"


class Alert:
    """Represents a single alert"""
    
    def __init__(self, 
                 alert_type: str,
                 severity: str,  # "info", "warning", "critical"
                 message: str,
                 details: Dict[str, Any] = None):
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp
        }
    
    def log(self):
        """Log alert to console"""
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨"
        }
        icon = icons.get(self.severity, "📢")
        LOG.info(f"{icon} [{self.severity.upper()}] {self.alert_type}: {self.message}")


class AlertThresholds:
    """Configurable thresholds for alert detection"""
    
    # Article velocity (articles per hour)
    BREAKING_NEWS_VELOCITY = 50  # More than 50 articles/hour = breaking news
    HIGH_VOLUME_THRESHOLD = 100   # More than 100 articles/hour
    
    # Sentiment thresholds
    NEGATIVE_SPIKE_THRESHOLD = 0.30  # 30% negative = spike
    POSITIVE_SPIKE_THRESHOLD = 0.50  # 50% positive = unusual
    
    # Data quality
    MIN_ARTICLES_PER_DAY = 10  # Less than 10 = source issue
    MAX_NULL_PERCENTAGE = 0.05  # More than 5% nulls = quality issue


class AlertStore:
    """Store alerts in MongoDB"""
    
    def __init__(self, uri: str = None):
        self.client = MongoClient(uri or os.getenv("MONGODB_URI", "mongodb://mongodb:27017"))
        self.db = self.client["news_rt"]
        self.collection = self.db["alerts"]
    
    def store(self, alert: Alert) -> str:
        """Store alert and return document ID"""
        result = self.collection.insert_one(alert.to_dict())
        return str(result.inserted_id)
    
    def get_recent(self, hours: int = 24) -> List[Dict]:
        """Get alerts from the last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return list(self.collection.find(
            {"timestamp": {"$gte": cutoff}},
            sort=[("timestamp", -1)]
        ))
    
    def get_by_type(self, alert_type: str, limit: int = 10) -> List[Dict]:
        """Get alerts by type"""
        return list(self.collection.find(
            {"alert_type": alert_type},
            sort=[("timestamp", -1)],
            limit=limit
        ))


class AlertDetector:
    """Detects alerts based on pipeline metrics"""
    
    def __init__(self, mongodb_uri: str = None):
        uri = mongodb_uri or os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
        self.client = MongoClient(uri)
        self.analytics_db = self.client["news_analytics"]
        self.rt_db = self.client["news_rt"]
        self.thresholds = AlertThresholds()
    
    def check_all(self) -> List[Alert]:
        """Run all alert checks"""
        alerts = []
        
        alerts.extend(self.check_article_velocity())
        alerts.extend(self.check_sentiment_distribution())
        alerts.extend(self.check_source_health())
        alerts.extend(self.check_data_quality())
        
        return alerts
    
    def check_article_velocity(self) -> List[Alert]:
        """Check for unusual article volume"""
        alerts = []
        
        # Count articles in the last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        one_hour_ago_ts = int(one_hour_ago.timestamp() * 1000)
        
        recent_count = self.analytics_db.historical_articles.count_documents({
            "event_time": {"$gte": one_hour_ago_ts}
        })
        
        if recent_count >= self.thresholds.HIGH_VOLUME_THRESHOLD:
            alerts.append(Alert(
                alert_type=AlertType.HIGH_VOLUME,
                severity="warning",
                message=f"High article volume: {recent_count} articles in the last hour",
                details={"count": recent_count, "threshold": self.thresholds.HIGH_VOLUME_THRESHOLD}
            ))
        elif recent_count >= self.thresholds.BREAKING_NEWS_VELOCITY:
            alerts.append(Alert(
                alert_type=AlertType.BREAKING_NEWS,
                severity="info",
                message=f"Elevated article volume: {recent_count} articles/hour",
                details={"count": recent_count}
            ))
        
        return alerts
    
    def check_sentiment_distribution(self) -> List[Alert]:
        """Check for sentiment spikes"""
        alerts = []
        
        # Get recent sentiment distribution
        pipeline = [
            {"$match": {"sentiment": {"$exists": True}}},
            {"$group": {
                "_id": "$sentiment",
                "count": {"$sum": 1}
            }}
        ]
        
        results = list(self.analytics_db.historical_articles.aggregate(pipeline))
        
        total = sum(r["count"] for r in results)
        if total == 0:
            return alerts
        
        sentiment_pcts = {r["_id"]: r["count"] / total for r in results}
        
        negative_pct = sentiment_pcts.get("negative", 0)
        if negative_pct >= self.thresholds.NEGATIVE_SPIKE_THRESHOLD:
            alerts.append(Alert(
                alert_type=AlertType.SENTIMENT_SPIKE,
                severity="warning",
                message=f"Negative sentiment spike: {negative_pct:.1%} of articles",
                details={"negative_percentage": negative_pct, "distribution": sentiment_pcts}
            ))
        
        return alerts
    
    def check_source_health(self) -> List[Alert]:
        """Check if sources are producing articles"""
        alerts = []
        
        # Count articles per source in last 24 hours
        one_day_ago = datetime.now() - timedelta(days=1)
        one_day_ago_ts = int(one_day_ago.timestamp() * 1000)
        
        pipeline = [
            {"$match": {"event_time": {"$gte": one_day_ago_ts}}},
            {"$group": {
                "_id": "$source_domain",
                "count": {"$sum": 1}
            }}
        ]
        
        results = list(self.analytics_db.historical_articles.aggregate(pipeline))
        source_counts = {r["_id"]: r["count"] for r in results}
        
        expected_sources = ["bbc.com", "cnn.com", "theguardian.com", "reuters.com"]
        for source in expected_sources:
            count = source_counts.get(source, 0)
            if count < self.thresholds.MIN_ARTICLES_PER_DAY:
                alerts.append(Alert(
                    alert_type=AlertType.SOURCE_DOWN,
                    severity="warning",
                    message=f"Low article count from {source}: {count} in 24h",
                    details={"source": source, "count": count}
                ))
        
        return alerts
    
    def check_data_quality(self) -> List[Alert]:
        """Check for data quality issues"""
        alerts = []
        
        # Check for recent data quality results
        quality_results = self.rt_db.data_quality_results.find_one(
            sort=[("run_time", -1)]
        )
        
        if quality_results and not quality_results.get("success", True):
            alerts.append(Alert(
                alert_type=AlertType.DATA_QUALITY,
                severity="critical",
                message="Data quality check failed",
                details=quality_results.get("statistics", {})
            ))
        
        return alerts


class AlertConsumer:
    """
    Main alert consumer that runs continuously
    """
    
    def __init__(self, mongodb_uri: str = None,
                 check_interval_seconds: int = 60):
        uri = mongodb_uri or os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
        self.detector = AlertDetector(uri)
        self.store = AlertStore(uri)
        self.check_interval = check_interval_seconds
        self.running = False
    
    def start(self):
        """Start the alert consumer loop"""
        self.running = True
        LOG.info("="*60)
        LOG.info("🔔 ALERT CONSUMER STARTED")
        LOG.info(f"   Check interval: {self.check_interval}s")
        LOG.info("="*60)
        
        while self.running:
            try:
                self._check_and_alert()
            except Exception as e:
                LOG.error(f"Error in alert check: {e}")
            
            time.sleep(self.check_interval)
    
    def stop(self):
        """Stop the consumer"""
        self.running = False
        LOG.info("🛑 Alert consumer stopped")
    
    def _check_and_alert(self):
        """Run all checks and process alerts"""
        LOG.info("🔍 Running alert checks...")
        
        alerts = self.detector.check_all()
        
        if alerts:
            LOG.info(f"📢 {len(alerts)} alert(s) detected")
            for alert in alerts:
                alert.log()
                self.store.store(alert)
        else:
            LOG.info("✅ No alerts - system healthy")


def main():
    """Main entry point"""
    import os
    
    mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://mongodb:27017")
    check_interval = int(os.environ.get("CHECK_INTERVAL", "60"))
    
    consumer = AlertConsumer(
        mongodb_uri=mongodb_uri,
        check_interval_seconds=check_interval
    )
    
    try:
        consumer.start()
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    main()
