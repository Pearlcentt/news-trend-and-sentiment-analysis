#!/bin/bash
# Stop Presto server
# Usage: ./stop_presto.sh

set -e

PRESTO_HOME="${PRESTO_HOME:-/opt/presto}"

if [ ! -d "$PRESTO_HOME" ]; then
    echo "Error: PRESTO_HOME directory not found: $PRESTO_HOME"
    exit 1
fi

echo "Stopping Presto server..."
cd "$PRESTO_HOME"
./bin/launcher stop

echo "Presto server stopped."

