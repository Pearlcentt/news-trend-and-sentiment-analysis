#!/bin/bash
# Start Presto server
# Usage: ./start_presto.sh

set -e

PRESTO_HOME="${PRESTO_HOME:-/opt/presto}"
PRESTO_CONFIG_DIR="${PRESTO_CONFIG_DIR:-/etc/presto}"

if [ ! -d "$PRESTO_HOME" ]; then
    echo "Error: PRESTO_HOME directory not found: $PRESTO_HOME"
    exit 1
fi

if [ ! -d "$PRESTO_CONFIG_DIR" ]; then
    echo "Error: PRESTO_CONFIG_DIR not found: $PRESTO_CONFIG_DIR"
    exit 1
fi

echo "Starting Presto server..."
cd "$PRESTO_HOME"
./bin/launcher start

echo "Waiting for Presto to start..."
sleep 10

# Check if Presto is running
if curl -s http://localhost:8080/v1/info > /dev/null; then
    echo "Presto server started successfully!"
    echo "Web UI: http://localhost:8080"
    echo "CLI: presto --server localhost:8080 --catalog hive --schema default"
else
    echo "Warning: Presto may not have started correctly. Check logs in $PRESTO_HOME/var/log/"
fi

