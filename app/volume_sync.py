from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_VOLUME_DIR = Path(__file__).resolve().parents[1] / "data" / "wireguard_volume"


def get_wireguard_volume_dir() -> Path:
    raw_path = os.getenv("WIREGUARD_VOLUME_DIR", "").strip()
    if raw_path:
        return Path(raw_path).expanduser()
    return DEFAULT_VOLUME_DIR


def _safe_filename(filename: str) -> str:
    return Path(str(filename)).name


def _category_dir(category: str) -> Path:
    safe_category = _safe_filename(category).strip().replace(" ", "_") or "wireguard"
    return get_wireguard_volume_dir() / safe_category


def write_text_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
    return path


def export_config_text(category: str, filename: str, content: str) -> Path:
    safe_filename = _safe_filename(filename)
    if not safe_filename:
        raise ValueError("filename is required")
    return write_text_atomic(_category_dir(category) / safe_filename, content)


def remove_exported_config(category: str, filename: str) -> bool:
    safe_filename = _safe_filename(filename)
    if not safe_filename:
        return False

    path = _category_dir(category) / safe_filename
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def build_volume_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "volume_dir": str(get_wireguard_volume_dir()),
        "records": records,
    }


def write_volume_manifest(records: list[dict[str, Any]], filename: str = "manifest.json") -> Path:
    import json

    manifest = build_volume_manifest(records)
    return write_text_atomic(get_wireguard_volume_dir() / filename, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


def reload_wireguard_container() -> dict[str, Any]:
    command = os.getenv("WIREGUARD_VOLUME_RELOAD_COMMAND", "").strip()
    if not command:
        return {"ok": True, "action": "skipped", "details": "WIREGUARD_VOLUME_RELOAD_COMMAND is not set"}

    timeout_raw = os.getenv("WIREGUARD_VOLUME_RELOAD_TIMEOUT", "30").strip()
    try:
        timeout = max(int(timeout_raw), 1)
    except Exception:
        timeout = 30

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {"ok": False, "action": "reload_failed", "details": str(exc)}

    return {
        "ok": result.returncode == 0,
        "action": "reloaded" if result.returncode == 0 else "reload_failed",
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }
