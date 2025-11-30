// MongoDB schema definitions for speed layer collections
// These collections are populated by Spark Structured Streaming
// Run this script using: mongo news_rt mongodb_schema.js

// Switch to news_rt database
use news_rt;

// Create indexes for efficient queries
// Real-time trends collection
db.rt_trends.createIndex(
  { 
    bucket_date: 1, 
    window_start_epoch: 1, 
    topic_token: 1 
  },
  { 
    unique: true,
    name: "rt_trends_primary_idx"
  }
);

// Index for time-based queries
db.rt_trends.createIndex(
  { 
    bucket_date: 1, 
    window_start_epoch: 1 
  },
  { 
    name: "rt_trends_time_idx"
  }
);

// TTL index to auto-delete documents after 30 days
db.rt_trends.createIndex(
  { updated_at_epoch: 1 },
  { 
    expireAfterSeconds: 2592000,  // 30 days
    name: "rt_trends_ttl_idx"
  }
);

// Real-time sentiment by source collection
db.rt_sentiment_by_source.createIndex(
  { 
    bucket_date: 1, 
    window_start_epoch: 1, 
    source_domain: 1 
  },
  { 
    unique: true,
    name: "rt_sentiment_primary_idx"
  }
);

// Index for time-based queries
db.rt_sentiment_by_source.createIndex(
  { 
    bucket_date: 1, 
    window_start_epoch: 1 
  },
  { 
    name: "rt_sentiment_time_idx"
  }
);

// TTL index to auto-delete documents after 30 days
db.rt_sentiment_by_source.createIndex(
  { updated_at_epoch: 1 },
  { 
    expireAfterSeconds: 2592000,  // 30 days
    name: "rt_sentiment_ttl_idx"
  }
);

print("MongoDB schema and indexes created successfully!");

// Example document structure for rt_trends:
// {
//   "_id": ObjectId("..."),
//   "bucket_date": "2025-10-27",
//   "window_start_epoch": 1730049000000,
//   "window_end_epoch": 1730049600000,
//   "topic_token": "interest rates",
//   "article_count": 134,
//   "unique_sources": 12,
//   "avg_sentiment": -0.18,
//   "pos_share": 0.21,
//   "neg_share": 0.49,
//   "top_article_ids": ["a1b2c3d4-0f3e-...", "..."],
//   "watermark_epoch": 1730050000000,
//   "updated_at_epoch": 1730050012000
// }

// Example document structure for rt_sentiment_by_source:
// {
//   "_id": ObjectId("..."),
//   "bucket_date": "2025-10-27",
//   "window_start_epoch": 1730049000000,
//   "window_end_epoch": 1730049600000,
//   "source_domain": "reuters.com",
//   "article_count": 37,
//   "avg_sentiment": -0.22,
//   "updated_at_epoch": 1730050012000
// }

