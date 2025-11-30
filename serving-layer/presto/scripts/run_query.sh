#!/bin/bash
# Execute a Presto SQL query
# Usage: ./run_query.sh <query_file.sql> [catalog] [schema]

set -e

QUERY_FILE="${1}"
CATALOG="${2:-hive}"
SCHEMA="${3:-default}"
PRESTO_SERVER="${PRESTO_SERVER:-localhost:8080}"

if [ -z "$QUERY_FILE" ]; then
    echo "Usage: $0 <query_file.sql> [catalog] [schema]"
    exit 1
fi

if [ ! -f "$QUERY_FILE" ]; then
    echo "Error: Query file not found: $QUERY_FILE"
    exit 1
fi

echo "Executing query: $QUERY_FILE"
echo "Catalog: $CATALOG, Schema: $SCHEMA"
echo "---"

presto --server "$PRESTO_SERVER" \
       --catalog "$CATALOG" \
       --schema "$SCHEMA" \
       --file "$QUERY_FILE" \
       --output-format CSV_HEADER

