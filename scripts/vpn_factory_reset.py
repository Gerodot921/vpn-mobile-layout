#!/usr/bin/env python3
"""Factory reset for VPN state: wipe all WireGuard and personal configs."""

from __future__ import annotations

import json

from app.personal_configs import wipe_all_personal_configs
from app.wireguard import wipe_all_wireguard_state


def main() -> int:
    wg_result = wipe_all_wireguard_state(remove_server_peers=True)
    personal_result = wipe_all_personal_configs(remove_server_peers=True)

    summary = {
        "wireguard": wg_result,
        "personal": personal_result,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
