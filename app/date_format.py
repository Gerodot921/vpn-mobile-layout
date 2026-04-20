from __future__ import annotations

from datetime import datetime


def format_human_datetime(value: str | None) -> str:
    if not value:
        return "-"

    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return str(value)

    return parsed.strftime("%d.%m.%Y %H:%M:%S")
