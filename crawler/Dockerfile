FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY crawler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy crawler code
COPY crawler/*.py ./
COPY crawler/config.kafka.yaml ./config/

# Copy schema from schemas/ folder (build context is project root)
COPY schemas/news_raw.avsc ./schemas/

# Create state directory
RUN mkdir -p /app/state

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV SCHEMA_REGISTRY_URL=http://schema-registry:8081

# Run crawler
CMD ["python", "news_crawler.py", "--config", "/app/config/config.kafka.yaml", "--print-events"]
