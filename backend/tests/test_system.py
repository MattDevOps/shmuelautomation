from fastapi.testclient import TestClient


def test_system_returns_zeros_on_fresh_db(client: TestClient) -> None:
    r = client.get("/system")
    assert r.status_code == 200
    body = r.json()
    assert body["db_ok"] is True
    assert body["drive_connected"] is False
    assert body["drive_account_email"] is None
    assert body["queue_pending_count"] == 0
    assert body["queue_due_now_count"] == 0
    assert body["properties_available"] == 0
    assert body["properties_total"] == 0
    assert body["contacts_count"] == 0
    assert body["groups_active"] == 0
    assert body["environment"] == "development"


def test_system_counts_match_real_data(client: TestClient) -> None:
    # Create two properties (one available, one rented) → 1 available, 2 total,
    # and only the available one gets queued.
    client.post("/properties", json={"type": "rent", "price": "8500"})
    client.post(
        "/properties", json={"type": "rent", "price": "9000", "status": "rented"}
    )

    client.post("/contacts", json={"name": "Yossi", "segments": ["buyer"]})
    client.post("/contacts", json={"name": "Dani", "segments": ["renter"]})

    client.post(
        "/groups",
        json={
            "platform": "whatsapp",
            "audience": "rent",
            "name": "Active group",
            "active": True,
        },
    )
    inactive = client.post(
        "/groups",
        json={
            "platform": "whatsapp",
            "audience": "rent",
            "name": "Inactive group",
            "active": True,
        },
    ).json()
    client.patch(f"/groups/{inactive['id']}", json={"active": False})

    body = client.get("/system").json()
    assert body["properties_total"] == 2
    assert body["properties_available"] == 1
    assert body["queue_pending_count"] == 1  # rented one was not enqueued
    assert body["contacts_count"] == 2
    assert body["groups_active"] == 1
