from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from shmuel_backend.scheduler import (
    is_in_shabbat_block,
    next_post_slot,
    next_slot_after,
)

JLM = ZoneInfo("Asia/Jerusalem")


def jlm(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=JLM)


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_shabbat_block_friday_afternoon_to_saturday_evening() -> None:
    # 2026-05-08 is a Friday. Block runs from 13:00 Fri to 21:00 Sat.
    assert not is_in_shabbat_block(jlm(2026, 5, 8, 12, 30))  # Fri 12:30 OK
    assert is_in_shabbat_block(jlm(2026, 5, 8, 13, 0))  # Fri 13:00 — block start
    assert is_in_shabbat_block(jlm(2026, 5, 8, 22, 0))  # Fri 22:00 blocked
    assert is_in_shabbat_block(jlm(2026, 5, 9, 12, 0))  # Sat noon blocked
    assert is_in_shabbat_block(jlm(2026, 5, 9, 20, 59))  # Sat 20:59 blocked
    assert not is_in_shabbat_block(jlm(2026, 5, 9, 21, 0))  # Sat 21:00 OK
    assert not is_in_shabbat_block(jlm(2026, 5, 10, 8, 0))  # Sun morning OK
    assert not is_in_shabbat_block(jlm(2026, 5, 7, 20, 0))  # Thursday OK


def test_next_slot_after_picks_next_8am_or_8pm() -> None:
    # Tuesday 06:30 → next slot is Tuesday 08:00
    result = next_slot_after(jlm(2026, 5, 5, 6, 30))
    assert result == jlm(2026, 5, 5, 8, 0)

    # Tuesday 09:00 → next slot is Tuesday 20:00
    result = next_slot_after(jlm(2026, 5, 5, 9, 0))
    assert result == jlm(2026, 5, 5, 20, 0)

    # Tuesday 20:00 → next slot is Wednesday 08:00 (strictly after)
    result = next_slot_after(jlm(2026, 5, 5, 20, 0))
    assert result == jlm(2026, 5, 6, 8, 0)


def test_next_post_slot_skips_friday_evening_into_saturday_night() -> None:
    # Now: Friday 11:00 Jerusalem → next slot is Friday 13:00? No, 13:00 isn't a
    # slot — slots are 08:00 and 20:00. So next slot would be Friday 20:00, but
    # that falls in the Shabbat block. So scheduler skips to Saturday 21:00 +
    # the next slot, which is Sunday 08:00.
    now = jlm(2026, 5, 8, 11, 0).astimezone(UTC)
    result = next_post_slot(now, capacity_at={})
    expected = jlm(2026, 5, 10, 8, 0).astimezone(UTC)
    assert result == expected


def test_next_post_slot_friday_morning_still_fits_friday_8am() -> None:
    # Friday 06:30 → 08:00 is BEFORE 13:00 so it's allowed
    now = jlm(2026, 5, 8, 6, 30).astimezone(UTC)
    result = next_post_slot(now, capacity_at={})
    assert result == jlm(2026, 5, 8, 8, 0).astimezone(UTC)


def test_next_post_slot_skips_full_slot() -> None:
    # Tuesday 06:00 → 08:00 slot is at capacity; should jump to 20:00.
    morning = jlm(2026, 5, 5, 8, 0).astimezone(UTC)
    capacity = {morning: 3}  # default schedule_posts_per_slot is 3
    result = next_post_slot(jlm(2026, 5, 5, 6, 0).astimezone(UTC), capacity)
    assert result == jlm(2026, 5, 5, 20, 0).astimezone(UTC)


def test_next_post_slot_overflows_to_next_day_when_both_slots_full() -> None:
    morning = jlm(2026, 5, 5, 8, 0).astimezone(UTC)
    evening = jlm(2026, 5, 5, 20, 0).astimezone(UTC)
    capacity = {morning: 3, evening: 3}
    result = next_post_slot(jlm(2026, 5, 5, 6, 0).astimezone(UTC), capacity)
    assert result == jlm(2026, 5, 6, 8, 0).astimezone(UTC)


def test_next_post_slot_handles_naive_now_as_utc() -> None:
    # Caller passes naive datetime — function must treat it as UTC, not local.
    now_naive = datetime(2026, 5, 5, 6, 0)  # naive
    result = next_post_slot(now_naive, capacity_at={})
    # 06:00 UTC on 2026-05-05 = 09:00 Jerusalem (UTC+3 DST), so next slot is 20:00 Jlm
    expected_utc = jlm(2026, 5, 5, 20, 0).astimezone(UTC)
    assert result == expected_utc


def test_next_post_slot_returns_aware_utc() -> None:
    result = next_post_slot(utc(2026, 5, 5, 6, 0), capacity_at={})
    assert result.tzinfo is not None
    assert result.tzinfo.utcoffset(result).total_seconds() == 0
