#!/bin/bash
# Run this script on server startup to sync all WireGuard peers with DB
# Usage: bash /root/vpn-mobile-layout/scripts/server_startup_sync.sh

cd /root/vpn-mobile-layout || exit 1

echo "=== WireGuard Peer Startup Sync ==="
source .venv/bin/activate 2>/dev/null || source /root/.venv/bin/activate 2>/dev/null

if /root/vpn-mobile-layout/.venv/bin/python /root/vpn-mobile-layout/scripts/reconcile_peers.py --all-sources --fix --purge-extras; then
	echo "Startup sync completed"
else
	echo "Startup sync failed, continuing bot startup"
fi

echo "=== Sync Complete ==="
