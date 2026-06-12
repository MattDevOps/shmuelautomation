"""Tests for the DB-backed posting schedule config endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_returns_defaults(client: TestClient) -> None:
    body = client.get("/post-queue/schedule-config").json()
    assert body["timezone"] == "Asia/Jerusalem"
    assert body["morning_slot"] == "08:00"
    assert body["evening_slot"] == "20:00"
    assert body["posts_per_slot"] == 3
    assert body["friday_block_after"] == "13:00"
    assert body["saturday_resume_at"] == "21:00"


def test_put_updates_and_persists(client: TestClient) -> None:
    r = client.put(
        "/post-queue/schedule-config",
        json={
            "timezone": "Asia/Jerusalem",
            "morning_slot": "09:30",
            "evening_slot": "21:00",
            "posts_per_slot": 5,
            "friday_block_after": "12:00",
            "saturday_resume_at": "20:30",
        },
    )
    assert r.status_code == 200
    assert r.json()["morning_slot"] == "09:30"
    # Persisted on the next read.
    again = client.get("/post-queue/schedule-config").json()
    assert again["posts_per_slot"] == 5
    assert again["evening_slot"] == "21:00"


def test_put_rejects_bad_time_format(client: TestClient) -> None:
    r = client.put(
        "/post-queue/schedule-config",
        json={
            "timezone": "Asia/Jerusalem",
            "morning_slot": "8am",  # not HH:MM
            "evening_slot": "20:00",
            "posts_per_slot": 3,
            "friday_block_after": "13:00",
            "saturday_resume_at": "21:00",
        },
    )
    assert r.status_code == 422


def test_put_rejects_unknown_timezone(client: TestClient) -> None:
    r = client.put(
        "/post-queue/schedule-config",
        json={
            "timezone": "Mars/Olympus",
            "morning_slot": "08:00",
            "evening_slot": "20:00",
            "posts_per_slot": 3,
            "friday_block_after": "13:00",
            "saturday_resume_at": "21:00",
        },
    )
    assert r.status_code == 422


def test_put_rejects_zero_capacity(client: TestClient) -> None:
    r = client.put(
        "/post-queue/schedule-config",
        json={
            "timezone": "Asia/Jerusalem",
            "morning_slot": "08:00",
            "evening_slot": "20:00",
            "posts_per_slot": 0,
            "friday_block_after": "13:00",
            "saturday_resume_at": "21:00",
        },
    )
    assert r.status_code == 422
