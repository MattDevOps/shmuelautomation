"""Pure scheduler logic — no I/O, no DB.

Computes when a property should be posted, honoring:
- Twice-daily slots (default 08:00 and 20:00 Asia/Jerusalem)
- A capacity per slot (default 3)
- Shabbat block: no posts after Friday 13:00 local until Saturday 21:00 local

The block start/end times are intentionally generous around sundown so we
don't have to compute candle-lighting times. Configurable in settings.

All inputs and outputs that touch a wall-clock are timezone-aware.
"""
from collections.abc import Mapping
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from shmuel_backend.config import settings


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.schedule_tz)


def _parse_hm(s: str) -> time:
    h, m = s.split(":", 1)
    return time(int(h), int(m))


def _slot_times() -> list[time]:
    return sorted([
        _parse_hm(settings.schedule_morning_slot),
        _parse_hm(settings.schedule_evening_slot),
    ])


def is_in_shabbat_block(dt: datetime) -> bool:
    """Friday from `friday_block_after` until Saturday `saturday_resume_at`,
    in the configured local timezone. `dt` may be naive (interpreted as
    local) or aware (converted to local)."""
    local = _to_local(dt)
    block_start = _parse_hm(settings.schedule_friday_block_after)
    block_end = _parse_hm(settings.schedule_saturday_resume_at)
    weekday = local.weekday()  # Monday=0, ... Friday=4, Saturday=5, Sunday=6
    if weekday == 4 and local.time() >= block_start:
        return True
    return weekday == 5 and local.time() < block_end


def _to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz())
    return dt.astimezone(_tz())


def _to_utc(dt_local: datetime) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=_tz())
    return dt_local.astimezone(ZoneInfo("UTC"))


def next_slot_after(after_local: datetime) -> datetime:
    """Strictly-after: returns the next slot whose datetime > after_local.

    The result is local-tz-aware. Does NOT skip Shabbat or honor capacity.
    """
    if after_local.tzinfo is None:
        after_local = after_local.replace(tzinfo=_tz())
    slots = _slot_times()
    for offset_days in (0, 1, 2):
        day = after_local.date() + timedelta(days=offset_days)
        for s in slots:
            candidate = datetime.combine(day, s, tzinfo=_tz())
            if candidate > after_local:
                return candidate
    raise RuntimeError("scheduler exhausted lookahead")  # unreachable


def next_post_slot(
    now_utc: datetime,
    capacity_at: Mapping[datetime, int] | None = None,
) -> datetime:
    """Returns the next available slot strictly in the future, in UTC.

    `capacity_at` maps slot-start (UTC) to count of already-scheduled posts.
    Slots at or above `schedule_posts_per_slot` are skipped.

    `now_utc` may be naive (treated as UTC) or aware.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
    capacity_at = capacity_at or {}

    cursor_local = now_utc.astimezone(_tz())
    # Look ahead at most 30 days — sanity guard. In practice we land in a
    # week tops because there are 14 slots/week minus ~2 Shabbat slots.
    for _ in range(60):
        candidate_local = next_slot_after(cursor_local)
        if is_in_shabbat_block(candidate_local):
            cursor_local = candidate_local
            continue
        candidate_utc = candidate_local.astimezone(ZoneInfo("UTC"))
        if capacity_at.get(candidate_utc, 0) >= settings.schedule_posts_per_slot:
            cursor_local = candidate_local
            continue
        return candidate_utc
    raise RuntimeError("scheduler could not find a free slot in 60 hops")
