#!/usr/bin/env python3
"""Export current WireGuard configs to the configured volume directory.

Usage:
  python scripts/sync_wireguard_volume.py
  python scripts/sync_wireguard_volume.py --reload-container
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import wireguard
from app.personal_configs import list_active_personal_configs
from app.volume_sync import export_config_text, reload_wireguard_container, write_volume_manifest


def sync_volume(*, reload_container: bool) -> dict:
    exported: list[dict[str, str]] = []

    for profile in wireguard.list_wireguard_profiles():
        filename = str(profile.get("config_filename") or "")
        content = str(profile.get("config_text") or "")
        if not filename:
            continue
        export_config_text("wireguard", filename, content)
        exported.append({"category": "wireguard", "filename": filename})

    for record in list_active_personal_configs():
        if record.get("revoked_at"):
            continue
        filename = str(record.get("config_filename") or "")
        content = str(record.get("config_text") or "")
        if not filename:
            continue
        export_config_text("personal", filename, content)
        exported.append({"category": "personal", "filename": filename})

    manifest_path = write_volume_manifest(exported)
    reload_result = reload_wireguard_container() if reload_container else {"ok": True, "action": "skipped"}

    return {
        "ok": bool(reload_result.get("ok", True)),
        "exported": len(exported),
        "manifest": str(manifest_path),
        "reload": reload_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reload-container", action="store_true", help="Run WIREGUARD_VOLUME_RELOAD_COMMAND after sync")
    args = parser.parse_args()

    result = sync_volume(reload_container=args.reload_container)
    print(result)


if __name__ == "__main__":
    main()
