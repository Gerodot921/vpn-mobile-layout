#!/usr/bin/env python3
"""Remove personal configs that failed to add to server (added_to_server=0)."""

import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "storage.sqlite3"


def cleanup_dead_configs():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return False

    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Count dead configs
            result = conn.execute(
                "SELECT COUNT(*) FROM personal_configs WHERE added_to_server = 0"
            ).fetchone()
            dead_count = result[0] if result else 0

            if dead_count == 0:
                print("✓ No dead configs found")
                return True

            # Show which ones we're deleting
            dead_configs = conn.execute(
                "SELECT config_id, address FROM personal_configs WHERE added_to_server = 0"
            ).fetchall()
            print(f"Found {dead_count} dead configs to remove:")
            for config_id, address in dead_configs:
                print(f"  - {config_id}: {address}")

            # Delete them
            conn.execute("DELETE FROM personal_configs WHERE added_to_server = 0")
            conn.commit()
            print(f"✓ Removed {dead_count} dead configs")
            return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    success = cleanup_dead_configs()
    sys.exit(0 if success else 1)
