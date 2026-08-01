"""Bounded analytics helpers for the admin portal."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal


def daterange_days(days: Literal[7, 30, 90]) -> tuple[datetime, datetime]:
    """Return inclusive UTC window [start_of_day(today-(days-1)), now]."""
    now = datetime.now(UTC)
    start_day = now.date() - timedelta(days=days - 1)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
    return start, now


def iter_date_strings(start: datetime, end: datetime) -> list[str]:
    cursor = start.date()
    last = end.date()
    out: list[str] = []
    while cursor <= last:
        out.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return out


def empty_analytics_points(start: datetime, end: datetime) -> list[dict[str, Any]]:
    return [
        {
            "date": day,
            "daily_active_users": 0,
            "new_users": 0,
            "conversations": 0,
            "messages": 0,
            "document_uploads": 0,
            "rag_queries": 0,
            "memory_actions": 0,
            "tool_executions": 0,
            "tool_succeeded": 0,
            "tool_failed": 0,
            "ai_latency_ms": None,
            "retrieval_latency_ms": None,
            "first_token_latency_ms": None,
        }
        for day in iter_date_strings(start, end)
    ]


def merge_series(
    base: list[dict[str, Any]],
    rows: list[tuple[date | str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    index = {item["date"]: item for item in base}
    for day_key, values in rows:
        key = day_key.isoformat() if isinstance(day_key, date) else str(day_key)[:10]
        if key not in index:
            continue
        index[key].update(values)
    return [index[day] for day in sorted(index)]
