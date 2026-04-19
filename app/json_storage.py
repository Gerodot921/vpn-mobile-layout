from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


STORAGE_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "storage.sqlite3"
_state_lock = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_key(path: Path) -> str:
    return str(path.resolve())


def _connect() -> sqlite3.Connection:
    STORAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STORAGE_DB_PATH, timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS kv_store (
            storage_key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return connection


def _read_legacy_json(path: Path) -> Any | None:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _mirror_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_json_file(path: Path, default: Any) -> Any:
    storage_key = _normalize_key(path)
    with _state_lock:
        with _connect() as connection:
            row = connection.execute(
                "SELECT payload FROM kv_store WHERE storage_key = ?",
                (storage_key,),
            ).fetchone()
            if row is not None:
                try:
                    return json.loads(row[0])
                except Exception:
                    return default

            legacy_value = _read_legacy_json(path)
            if legacy_value is None:
                return default

            try:
                payload = json.dumps(legacy_value, ensure_ascii=False, sort_keys=True)
            except Exception:
                return default

            connection.execute(
                "INSERT OR REPLACE INTO kv_store (storage_key, payload, updated_at) VALUES (?, ?, ?)",
                (storage_key, payload, _now_iso()),
            )
            connection.commit()
            return legacy_value


def save_json_file(path: Path, data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    storage_key = _normalize_key(path)

    with _state_lock:
        with _connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO kv_store (storage_key, payload, updated_at) VALUES (?, ?, ?)",
                (storage_key, payload, _now_iso()),
            )
            connection.commit()

    _mirror_json_file(path, data)