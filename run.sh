#!/bin/bash
set -e

if [ ! -f /data/options.json ]; then
    echo "ERROR: /data/options.json not found. Are you running outside Home Assistant?"
    echo "Run the base container directly for command-line use:"
    echo "  podman run --rm --env-file .env akahu-to-budget"
    exit 1
fi

echo "Reading configuration from /data/options.json"

while IFS= read -r entry; do
    key=$(printf '%s' "$entry" | base64 -d | jq -r '.key')
    value=$(printf '%s' "$entry" | base64 -d | jq -r '.value | tostring')
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "ERROR: Invalid option key for environment export: $key"
        exit 1
    fi
    export "$key=$value"
done < <(jq -r 'to_entries[] | select(.key != "sync_interval") | @base64' /data/options.json)

SYNC_INTERVAL=$(jq -r '.sync_interval // 86400' /data/options.json)

echo "Sync interval: ${SYNC_INTERVAL}s"
echo "Starting sync loop..."

while true; do
    echo "=== Sync started at $(date -u) ==="
    python /app/sync_cli.py || echo "Sync failed (will retry in ${SYNC_INTERVAL}s)"
    echo "=== Sync finished, sleeping ${SYNC_INTERVAL}s ==="
    sleep "$SYNC_INTERVAL"
done
