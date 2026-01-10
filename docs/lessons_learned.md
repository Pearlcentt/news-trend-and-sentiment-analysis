# 📚 Lessons Learned

This document captures the technical challenges, solutions, and insights gained during the development of the News Trend & Sentiment Analysis pipeline.

---

## 1. Lessons on Data Ingestion

### Lesson 1: Handling Multilingual GDELT Data

#### Problem Description

- **Context**: The crawler ingests data from GDELT and RSS feeds, expecting English content.
- **Challenges**: Domain filtering (e.g., `cnn.com`) was insufficient as `edition.cnn.com` or international subdomains served Spanish/Arabic content.
- **System Impact**: Downstream NLP models (Sentiment/Classification) failed or produced garbage results on non-English text.

#### Approaches Tried

- **Approach 1**: Strict domain allowlist. _Result_: Failed, as trusted domains host multi-language content.
- **Approach 2**: Python `langdetect` library. _Result_: Accurate but added significant latency per article.
- **Trade-offs**: Latency vs. Accuracy.

#### Final Solution

- **Solution**: Implemented a lightweight filter using the `language` field provided in the feed metadata combined with a restricted parsing logic.
- **Implementation**: `if language and language.lower() != 'english': return None` in the crawler parser.
- **Results**: 99.5% English content without external library overhead.

#### Key Takeaways

- **Insight**: Never assume "Global" news sources are Monolingual.
- **Recommendation**: Filter at the earliest possible point (ingestion) to save processing resources.

---

## 2. Lessons on Data Processing with Spark

### Lesson 2: Logic Redundancy in Analytics Jobs

#### Problem Description

- **Context**: Separate jobs for `graph_analytics` and `ml_pipeline` existed.
- **Challenges**: Logic for loading data and basic preprocessing was duplicated across multiple files.
- **System Impact**: Code maintenance was difficult; changing a schema required edits in 3+ files.

#### Approaches Tried

- **Approach 1**: Copy-paste utility functions. _Result_: Tech debt accumulation.
- **Approach 2**: Modular refactoring. _Result_: Cleaner codebase.

#### Final Solution

- **Solution**: Consolidated common logic into `advanced_aggregations.py` and imported specific modules.
- **Implementation**: Created a unified `integrated_analytics` Airflow task that orchestrates the flow.
- **Results**: Reduced total lines of code by ~30% and simplified the Airflow DAG.

#### Key Takeaways

- **Insight**: Spark jobs should be treated as software modules, not just scripts.
- **Recommendation**: Use Python modules and `--py-files` or Docker image packaging for shared logic.

---

## 3. Lessons on Stream Processing

### Lesson 3: Missing Categories in Real-Time Data

#### Problem Description

- **Context**: The Streaming pipeline is lightweight and lacked the heavy ML model used in Batch.
- **Challenges**: Real-time articles defaulted to "General" category, making the dashboard look broken.
- **System Impact**: Poor user experience; "Trending Categories" chart was useless for real-time data.

#### Approaches Tried

- **Approach 1**: Load full ML model in Streaming. _Result_: OOM kills and high latency.
- **Approach 2**: Default to "Uncategorized". _Result_: Honest but unhelpful.

#### Final Solution

- **Solution**: Implemented a lightweight, keyword-based UDF (`categorize_article`).
- **Implementation**: A Spark UDF maps keywords (e.g., "election" -> "Politics") directly in the streaming micro-batch.
- **Results**: Immediate, reasonably accurate categorization with <5ms latency.

#### Key Takeaways

- **Insight**: Speed Layer sometimes requires approximation over perfection (Lambda Architecture principle).
- **Recommendation**: Use heuristics for speed, models for accuracy.

---

## 4. Lessons on Data Storage

### Lesson 4: The "Serving Layer" Gaps

#### Problem Description

- **Context**: Batch jobs wrote to Parquet (Data Lake) for archival.
- **Challenges**: The Dashboard needed low-latency access to _processed_ batch data, but reading Parquet from Spark-on-K8s storage was slow/complex for Streamlit.
- **System Impact**: Dashboard showed stale or missing historical data.

#### Approaches Tried

- **Approach 1**: Streamlit reads Parquet directly. _Result_: Slow, concurrency issues.
- **Approach 2**: Batch Job Dual-Write. _Result_: Success.

#### Final Solution

- **Solution**: Modified `batch_pipeline.py` to write to **both** HDFS/Parquet (Archive) and MongoDB (Serving).
- **Implementation**: Added `spark.write.format("mongodb")...save()` after the Parquet write step.
- **Results**: Dashboard queries MongoDB (fast indexed) while Data Scientists can query Parquet.

#### Key Takeaways

- **Insight**: Write for the reader. optimize storage based on access patterns.
- **Recommendation**: Use Dual-Write strategies to bridge the gap between Data Lake and Serving Layer.

---

## 5. Lessons on System Integration

### Lesson 5: Airflow DAG Synchronization

#### Problem Description

- **Context**: Updating DAG code locally did not reflect in the Airflow Scheduler running in K8s.
- **Challenges**: `KubernetesPodOperator` was running old code; Scheduler was throwing `DagNotFound` after restarts.
- **System Impact**: Pipeline failed to trigger or ran obsolete logic.

#### Approaches Tried

- **Approach 1**: Editing files inside the pod. _Result_: Lost on restart (ephemeral).
- **Approach 2**: ConfigMap mounts. _Result_: Robust syncing.

#### Final Solution

- **Solution**: Mounted DAGs and Code via Kubernetes ConfigMaps (`airflow-dags`, `spark-jobs-code`).
- **Implementation**: A `create-configmaps.sh` script updates the ConfigMap, and we restart pods to pick up changes.
- **Results**: rapid development cycle; code is versioned in Git and synced to K8s.

#### Key Takeaways

- **Insight**: In K8s, Code is Data. Manage it via ConfigMaps or Image Builds.
- **Recommendation**: For dev, ConfigMaps are faster than rebuilding Docker images.

---

## 6. Lessons on Performance Optimization

### Lesson 6: Minikube Resource Exhaustion

#### Problem Description

- **Context**: Running Kafka, Spark, MongoDB, Airflow, and Trino on a single node.
- **Challenges**: Pods constantly entered `CrashLoopBackOff` or `Evicted` states.
- **System Impact**: Unstable pipeline; inability to run concurrent jobs.

#### Approaches Tried

- **Approach 1**: Increase Docker RAM limits. _Result_: Helped, but hit physical hardware limits.
- **Approach 2**: Service pruning. _Result_: Success.

#### Final Solution

- **Solution**: Scaled down non-essential services (Trino, Grafana, multiple Spark Workers) when focusing on the core pipeline.
- **Implementation**: `kubectl scale deployment trino --replicas=0`.
- **Results**: Freed up ~4GB RAM, allowing Airflow and Spark to run reliably.

#### Key Takeaways

- **Insight**: Local Big Data dev environments require strict resource budgeting.
- **Recommendation**: Define "Profiles" (e.g., Core vs. Analytics) and scale services accordingly.

---

## 7. Lessons on Monitoring & Debugging

### Lesson 7: "Silent" Data Failures

#### Problem Description

- **Context**: Visualization looked fine, but data was stale (dates were wrong).
- **Challenges**: No obvious errors in logs; the pipeline was "working" but producing bad data.
- **System Impact**: Dashboard showed "Recently Updated" but displayed content from 2023 (RSS feed pollution).

#### Approaches Tried

- **Approach 1**: Manual daily checks. _Result_: Unreliable.
- **Approach 2**: Metadata validation. _Result_: Better visibility.

#### Final Solution

- **Solution**: Added explicit Date Parsing and Validation in the crawler; visualized "Last Update" KPI in Dashboard.
- **Implementation**: Crawler now discards articles >7 days old; Dashboard highlights "Real-Time" vs "Historical" distinctively.
- **Results**: Trusted data display; immediate visual feedback if ingestion stalls.

#### Key Takeaways

- **Insight**: "Success" exit code != Correct Data.
- **Recommendation**: Monitor business metrics (e.g., "Freshness"), not just system metrics (CPU/RAM).

---

## 8. Lessons on Scaling

### Lesson 8: Vertical vs. Horizontal for Spark

#### Problem Description

- **Context**: ML classification task was slow (single executor).
- **Challenges**: Increasing executor count (Horizontal) in Minikube caused thrashing.
- **System Impact**: Job took 20+ mins for small datasets.

#### Approaches Tried

- **Approach 1**: Add more executors. _Result_: OOM Kills.
- **Approach 2**: Vertical scaling (More cores per executor). _Result_: Better locally.

#### Final Solution

- **Solution**: Optimized `spark-submit` to use local mode `local[2]` for specific tasks to avoid overhead of distributed scheduling on a single node.
- **Implementation**: Adjusted `integrated_analytics` task to run in-process driver mode for small batches.
- **Results**: Reduced overhead; job completion <5 mins.

#### Key Takeaways

- **Insight**: Distributed computing overhead is real. For small data (<10GB), single-node processing is often faster.
- **Recommendation**: Don't distribute until you have to.

---

## 9. Lessons on Data Quality & Testing

### Lesson 9: Encoding Issues (The Warning Signs)

#### Problem Description

- **Context**: Dashboard displayed "???" instead of emojis or specific characters.
- **Challenges**: Docker containers defaulted to `POSIX` locale (ASCII).
- **System Impact**: Unprofessional UI; potential data corruption for non-Latin scripts.

#### Approaches Tried

- **Approach 1**: ignoring it. _Result_: UI looked buggy.
- **Approach 2**: Setting Env Vars. _Result_: Fixed.

#### Final Solution

- **Solution**: Explicitly set `ENV LANG=C.UTF-8` in Dockerfiles.
- **Implementation**: Updated `dashboard/Dockerfile`.
- **Results**: Emojis (📊, 🚀) render correctly.

#### Key Takeaways

- **Insight**: Locale defaults in minimal Docker images (like `slim`) are dangerous.
- **Recommendation**: Always enforce UTF-8 in Dockerfiles.

---

## 10. Lessons on Fault Tolerance

### Lesson 10: Automated Data Lifecycle

#### Problem Description

- **Context**: Real-time data accumulates indefinitely in MongoDB.
- **Challenges**: `news_rt` collection grew unbounded; data became stale/irrelevant after 24 hours.
- **System Impact**: Wasted storage; slower queries.

#### Approaches Tried

- **Approach 1**: Manual drop. _Result_: Forgot to do it.
- **Approach 2**: TTL Index. _Result_: Good, but hard to manage with complex conditions.

#### Final Solution

- **Solution**: Airflow Scheduled Cleanup Task.
- **Implementation**: Added `cleanup_rt_data` task to the daily DAG to delete records >3 days old.
- **Results**: Self-cleaning system; storage usage remains constant over time.

#### Key Takeaways

- **Insight**: Data requires garbage collection just like memory.
- **Recommendation**: Build "End of Life" logic into the pipeline from Day 1.
