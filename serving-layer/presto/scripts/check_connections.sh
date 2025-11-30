#!/bin/bash
# Check Presto connections to HDFS and MongoDB
# Usage: ./check_connections.sh

set -e

PRESTO_SERVER="${PRESTO_SERVER:-localhost:8080}"

echo "Checking Presto server status..."
if ! curl -s "http://$PRESTO_SERVER/v1/info" > /dev/null; then
    echo "Error: Presto server is not running at $PRESTO_SERVER"
    exit 1
fi
echo "✓ Presto server is running"

echo ""
echo "Checking Hive catalog (HDFS)..."
presto --server "$PRESTO_SERVER" --execute "SHOW CATALOGS" | grep -q hive && echo "✓ Hive catalog found" || echo "✗ Hive catalog not found"

echo ""
echo "Checking MongoDB catalog..."
presto --server "$PRESTO_SERVER" --execute "SHOW CATALOGS" | grep -q mongodb && echo "✓ MongoDB catalog found" || echo "✗ MongoDB catalog not found"

echo ""
echo "Listing Hive schemas..."
presto --server "$PRESTO_SERVER" --catalog hive --execute "SHOW SCHEMAS" || echo "✗ Cannot connect to Hive"

echo ""
echo "Listing MongoDB schemas..."
presto --server "$PRESTO_SERVER" --catalog mongodb --execute "SHOW SCHEMAS" || echo "✗ Cannot connect to MongoDB"

echo ""
echo "Connection check complete!"

