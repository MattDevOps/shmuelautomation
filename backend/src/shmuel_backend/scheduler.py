"""Pure scheduler logic — no I/O, no DB.

Computes when a property should be posted, honoring:
- Twice-daily slots (default 08:00 and 20:00 Asia/Jerusalem)
- A capacity per slot (default 3)
- Shabbat block: no posts after Friday 13:00 local until Saturday 21:00 local

The numbers come from a `SchedulePolicy`. Callers that have a DB-backed schedule
pass one in; everything defaults to the env-based `settings` when omitted, so
existing call sites and tests keep working unchanged.

All inputs and outputs that touch a wall-clock are timezone-aware.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from shmuel_backend.config import settings


@dataclass(frozen=True)
class SchedulePolicy:
    """Effective posting schedule. Times are 'HH:MM' in `tz`."""

    tz: str
    morning_slot: str
    evening_slot: str
    posts_per_slot: int
    friday_block_after: str
    saturday_resume_at: str

    @classmethod
    def from_settings(cls) -> "SchedulePolicy":
        return cls(
            tz=settings.schedule_tz,
            morning_slot=settings.schedule_morning_slot,
            evening_slot=settings.schedule_evening_slot,
            posts_per_slot=settings.schedule_posts_per_slot,
            friday_block_after=settings.schedule_friday_block_after,
            saturday_resume_at=settings.schedule_saturday_resume_at,
        )


def _resolve(policy: SchedulePolicy | None) -> SchedulePolicy:
    return policy or SchedulePolicy.from_settings()


def _parse_hm(s: str) -> time:
    h, m = s.split(":", 1)
    return time(int(h), int(m))


def _slot_times(policy: SchedulePolicy) -> list[time]:
    return sorted([
        _parse_hm(policy.morning_slot),
        _parse_hm(policy.evening_slot),
    ])


def _to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def is_in_shabbat_block(
    dt: datetime, policy: SchedulePolicy | None = None
) -> bool:
    """Friday from `friday_block_after` until Saturday `saturday_resume_at`,
    in the configured local timezone. `dt` may be naive (interpreted as
    local) or aware (converted to local)."""
    policy = _resolve(policy)
    local = _to_local(dt, ZoneInfo(policy.tz))
    block_start = _parse_hm(policy.friday_block_after)
    block_end = _parse_hm(policy.saturday_resume_at)
    weekday = local.weekday()  # Monday=0, ... Friday=4, Saturday=5, Sunday=6
    if weekday == 4 and local.time() >= block_start:
        return True
    return weekday == 5 and local.time() < block_end


def next_slot_after(
    after_local: datetime, policy: SchedulePolicy | None = None
) -> datetime:
    """Strictly-after: returns the next slot whose datetime > after_local.

    The result is local-tz-aware. Does NOT skip Shabbat or honor capacity.
    """
    policy = _resolve(policy)
    tz = ZoneInfo(policy.tz)
    if after_local.tzinfo is None:
        after_local = after_local.replace(tzinfo=tz)
    slots = _slot_times(policy)
    for offset_days in (0, 1, 2):
        day = after_local.date() + timedelta(days=offset_days)
        for s in slots:
            candidate = datetime.combine(day, s, tzinfo=tz)
            if candidate > after_local:
                return candidate
    raise RuntimeError("scheduler exhausted lookahead")  # unreachable


def next_post_slot(
    now_utc: datetime,
    capacity_at: Mapping[datetime, int] | None = None,
    policy: SchedulePolicy | None = None,
) -> datetime:
    """Returns the next available slot strictly in the future, in UTC.

    `capacity_at` maps slot-start (UTC) to count of already-scheduled posts.
    Slots at or above `policy.posts_per_slot` are skipped.

    `now_utc` may be naive (treated as UTC) or aware.
    """
    policy = _resolve(policy)
    tz = ZoneInfo(policy.tz)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=ZoneInfo("UTC"))
    capacity_at = capacity_at or {}

    cursor_local = now_utc.astimezone(tz)
    # Look ahead at most 30 days — sanity guard. In practice we land in a
    # week tops because there are 14 slots/week minus ~2 Shabbat slots.
    for _ in range(60):
        candidate_local = next_slot_after(cursor_local, policy)
        if is_in_shabbat_block(candidate_local, policy):
            cursor_local = candidate_local
            continue
        candidate_utc = candidate_local.astimezone(ZoneInfo("UTC"))
        if capacity_at.get(candidate_utc, 0) >= policy.posts_per_slot:
            cursor_local = candidate_local
            continue
        return candidate_utc
    raise RuntimeError("scheduler could not find a free slot in 60 hops")
