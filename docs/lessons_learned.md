# 📚 Lessons Learned

Insights and solutions discovered while building and fixing the News Trend & Sentiment Analysis pipeline.

---

## 🔧 Critical Fixes & Debugging

### 1. Non-English Articles Appearing

**Problem**: GDELT domain filter (bbc.com, cnn.com) returned Spanish, Arabic, and other languages from international editions.

**Root Cause**: Domain filter alone doesn't guarantee English content. CNN has cnn.com (English) and edition.cnn.com (multilingual).

**Solution**:

```python
# Filter by language field in parser
language = item.get("language", "").lower()
if language and language != "english":
    return None
```

**Lesson**: Always add language filtering at the parser level, not just API level.

---

### 2. Wrong Article Dates (April 2023 appearing)

**Problem**: Fresh RSS articles showed dates from 2023 instead of current dates.

**Root Cause**: Some RSS feeds include old/archived articles in their feed. The crawler was accepting all entries regardless of age.

**Solution**:

```python
# 7-day date filter
seven_days_ago = int((datetime.now().timestamp() - 7*24*60*60) * 1000)
if pub_timestamp < seven_days_ago:
    continue  # Skip old articles
```

**Lesson**: Never trust RSS feed freshness—always validate dates.

---

### 3. Dates Showing Crawl Time Instead of Published Time

**Problem**: Dashboard showed articles dated "2025-12-30" (today) instead of actual publication date.

**Root Cause**: `_update_realtime_db()` was storing `process_time: datetime.now()` instead of the article's `published_at`.

**Fix**:

```python
# Before (wrong)
"process_time": datetime.now()

# After (correct)
pub_time = article.get('published_at') or article.get('event_time')
"process_time": datetime.fromtimestamp(pub_time / 1000)
```

**Lesson**: Always trace date fields through the entire pipeline.

---

### 4. Raw HTML in Article Content

**Problem**: "View Full Article" displayed raw tags like `<p>`, `</p>`, `<a href=...>`.

**Solution**: Created `strip_html_tags()` function:

```python
def strip_html_tags(html_text):
    text = re.sub(r'<a[^>]*>Continue reading[^<]*</a>', '', html_text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()
```

**Lesson**: HTML content needs sanitization before display.

---

### 5. SSL Certificate Error (GDELT API)

**Problem**: `[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired`

**Root Cause**: GDELT's SSL certificate wasn't updated.

**Solution**:

```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
self.session.verify = False
```

**Lesson**: External APIs can fail unexpectedly—add fallback/retry logic.

---

## 🏗️ Architecture Decisions

### Lambda Architecture Implementation

| Layer       | Component                                   | Purpose             |
| ----------- | ------------------------------------------- | ------------------- |
| **Speed**   | `06-crawler.yaml` → Kafka → Spark Streaming | Real-time updates   |
| **Batch**   | `14-*-job.yaml` → MongoDB → Spark Batch     | Historical backfill |
| **Serving** | MongoDB + Streamlit                         | Query and display   |

**Lesson**: Separate streaming (continuous) and batch (one-shot) jobs for clarity.

### Kubernetes Over Docker Compose

- K8s provides better service discovery, scaling, and restart policies
- Port-forwarding is simpler than NodePort for local development
- `imagePullPolicy: Never` is essential for Minikube + local images

**Lesson**: Start with K8s from day one if targeting production.

---

## 💾 Data Quality

### Filter Chain

```
[Domain Filter] → [Language Filter] → [Date Filter] → [HTML Strip] → [MongoDB]
```

Each filter catches different issues:

1. **Domain**: Limits to trusted sources
2. **Language**: Removes non-English
3. **Date**: Removes stale articles
4. **HTML Strip**: Cleans content for display

**Lesson**: Data quality requires multiple layers of filtering.

### Schema Validation

- Avro schemas for Kafka provide contract enforcement
- MongoDB lacks schema—rely on application-level validation
- Great Expectations (future) for formal data quality checks

---

## 🎨 Dashboard Development

### Key Improvements Made

| Issue              | Solution                         |
| ------------------ | -------------------------------- |
| Truncated articles | Removed 5000-char limit          |
| Raw HTML display   | Added `strip_html_tags()`        |
| Wrong dates        | Prioritized `published_at` field |
| "Unknown" sources  | Fixed real-time trends filter    |

### Light Theme > Dark Theme

- Initial dark theme was hard to read
- Light theme with soft grays is more professional
- Users prefer readability over style

---

## 🐳 Kubernetes Tips

### Image Building

```powershell
# Build directly in Minikube (not Docker Desktop)
minikube image build -t news-dashboard:latest ./dashboard
```

### Pod Restart After Changes

```powershell
kubectl delete pod -n news-pipeline -l app=streamlit-dashboard
```

### Port-Forward for Access

```powershell
kubectl port-forward -n news-pipeline svc/streamlit-dashboard 8501:8501
```

---

## ✅ Best Practices Discovered

1. **Always store article content**, not just URLs (articles expire)
2. **Filter at multiple levels** (API, parser, storage)
3. **Use upsert** instead of insert (idempotent operations)
4. **Add date validation** for all external data
5. **Strip HTML** before text display
6. **Test with real data** (not just mocks)
7. **Keep Airflow for scheduling** (daily batch jobs)
8. **Maintain tests** (unit + integration)

---

## 🎯 What We'd Do Differently

1. **Validate dates at ingestion** (not discovery phase)
2. **Add language detection library** (langdetect) as backup
3. **Use structured logging** for easier debugging
4. **Implement health endpoints** for all services
5. **Add retry logic** for external API calls
6. **Use Helm charts** for easier K8s management

---

## 📈 Future Roadmap

### High Priority (Recommended)

- [ ] **Great Expectations formal** - Full integration with checkpoints
- [ ] **Real-time alerts** - Breaking news detection via Kafka
- [ ] **CI/CD with ArgoCD** - GitOps deployments

### Medium Priority

- [ ] **Cloud deployment** (EKS/GKE)
- [ ] **LLM summarization** (GPT/Claude)

### Low Priority

- [ ] **Multi-language support**

---

**Last Updated**: 2025-12-31
