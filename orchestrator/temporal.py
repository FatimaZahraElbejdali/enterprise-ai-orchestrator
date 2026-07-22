from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _coerce_now(now: datetime | None = None, timezone_name: str | None = None) -> datetime:
    tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc

    if now is None:
        return datetime.now(tz)

    if now.tzinfo is None:
        return now.replace(tzinfo=tz)

    return now.astimezone(tz)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def resolve_relative_period(
    constraint: dict,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> dict:
    if not isinstance(constraint, dict):
        raise ValueError("invalid_temporal_constraint")

    if constraint.get("type") != "relative_period":
        raise ValueError("unsupported_temporal_constraint")

    period = str(constraint.get("period") or "").strip().lower()

    try:
        offset = int(constraint.get("offset") or 0)
    except (TypeError, ValueError):
        raise ValueError("invalid_temporal_offset") from None

    current = _coerce_now(now, timezone_name)

    if period == "day":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=offset)
        end = start + timedelta(days=1)
    elif period == "week":
        start_of_week = current - timedelta(days=current.weekday())
        start = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=offset)
        end = start + timedelta(weeks=1)
    elif period == "month":
        month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start = _add_months(month_start, offset)
        end = _add_months(start, 1)
    elif period == "year":
        year_start = current.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        start = year_start.replace(year=year_start.year + offset)
        end = start.replace(year=start.year + 1)
    else:
        raise ValueError("unsupported_temporal_period")

    return {
        "type": "half_open_interval",
        "start": start,
        "end": end,
        "period": period,
        "offset": offset,
        "timezone": str(current.tzinfo),
    }
