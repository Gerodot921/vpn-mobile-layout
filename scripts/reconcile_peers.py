#!/usr/bin/env python3
"""
Small CLI to reconcile WireGuard peers from DB to server.
Usage:
  python scripts/reconcile_peers.py --user 12345 --fix
  python scripts/reconcile_peers.py --all --dry-run
"""
import os
import sys
import argparse

# Ensure project root is on sys.path so `from app import wireguard` works
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_dotenv(path: str) -> None:
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k.startswith("WIREGUARD_") and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


_load_dotenv(os.path.join(ROOT, ".env"))

from app import wireguard


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", type=int, help="User ID to reconcile")
    p.add_argument("--all", action="store_true", help="Reconcile all DB profiles")
    p.add_argument("--sync", action="store_true", help="Deprecated: startup sync is disabled")
    p.add_argument("--fix", action="store_true", help="Apply fixes (remove/add) rather than dry-run")
    args = p.parse_args()

    if args.sync:
        print("Sync mode is disabled")
        return

    if not args.user and not args.all:
        p.error("--user, --all, or --sync required")

    if args.user:
        res = wireguard.reconcile_user_peer(args.user, fix=args.fix)
        print(res)
        return

    state = wireguard._load_state()
    for user_key, profile in state.get('profiles', {}).items():
        uid = int(user_key)
        res = wireguard.reconcile_user_peer(uid, fix=args.fix)
        print(f"{uid}: {res}")


if __name__ == "__main__":
    main()
