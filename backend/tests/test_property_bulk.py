import uuid

from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "neighborhood": "Baka",
    }
    base.update(overrides)
    r = client.post("/properties", json=base)
    assert r.status_code == 201, r.text
    return r.json()


def test_bulk_status_marks_all_rented(client: TestClient) -> None:
    a = _create(client)
    b = _create(client)
    c = _create(client)

    r = client.post(
        "/properties/bulk/status",
        json={"ids": [a["id"], b["id"], c["id"]], "status": "rented"},
    )
    assert r.status_code == 200
    assert r.json() == {"affected": 3, "not_found": []}

    for p in (a, b, c):
        got = client.get(f"/properties/{p['id']}").json()
        assert got["status"] == "rented"


def test_bulk_status_reports_not_found_without_aborting(client: TestClient) -> None:
    a = _create(client)
    missing = str(uuid.uuid4())
    r = client.post(
        "/properties/bulk/status",
        json={"ids": [a["id"], missing], "status": "sold"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["affected"] == 1
    assert body["not_found"] == [missing]
    assert client.get(f"/properties/{a['id']}").json()["status"] == "sold"


def test_bulk_status_cancels_queue_when_leaving_available(
    client: TestClient,
) -> None:
    """A new available property gets enqueued; marking it sold should
    cancel that pending post — same as the single-row PATCH does."""
    p = _create(client)
    # /post-queue only returns pending slots, so any row matching the
    # property id is by definition pending.
    pending_before = [
        s for s in client.get("/post-queue").json() if s["property_id"] == p["id"]
    ]
    assert len(pending_before) >= 1

    client.post(
        "/properties/bulk/status",
        json={"ids": [p["id"]], "status": "sold"},
    )
    pending_after = [
        s for s in client.get("/post-queue").json() if s["property_id"] == p["id"]
    ]
    assert pending_after == []


def test_bulk_status_requeues_when_returning_to_available(
    client: TestClient,
) -> None:
    p = _create(client)
    # Leave available → pending posts cancelled
    client.post(
        "/properties/bulk/status",
        json={"ids": [p["id"]], "status": "rented"},
    )
    # Back to available → fresh slot
    client.post(
        "/properties/bulk/status",
        json={"ids": [p["id"]], "status": "available"},
    )
    pending = [
        s for s in client.get("/post-queue").json() if s["property_id"] == p["id"]
    ]
    assert len(pending) >= 1


def test_bulk_delete_removes_all(client: TestClient) -> None:
    a = _create(client)
    b = _create(client)
    r = client.post(
        "/properties/bulk/delete", json={"ids": [a["id"], b["id"]]}
    )
    assert r.status_code == 200
    assert r.json() == {"affected": 2, "not_found": []}
    assert client.get(f"/properties/{a['id']}").status_code == 404
    assert client.get(f"/properties/{b['id']}").status_code == 404


def test_bulk_delete_partial(client: TestClient) -> None:
    a = _create(client)
    missing = str(uuid.uuid4())
    r = client.post(
        "/properties/bulk/delete", json={"ids": [a["id"], missing]}
    )
    assert r.json() == {"affected": 1, "not_found": [missing]}


def test_bulk_endpoints_reject_empty_ids(client: TestClient) -> None:
    assert (
        client.post(
            "/properties/bulk/status", json={"ids": [], "status": "sold"}
        ).status_code
        == 422
    )
    assert (
        client.post("/properties/bulk/delete", json={"ids": []}).status_code
        == 422
    )


def test_bulk_endpoints_reject_invalid_status(client: TestClient) -> None:
    a = _create(client)
    r = client.post(
        "/properties/bulk/status",
        json={"ids": [a["id"]], "status": "demolished"},
    )
    assert r.status_code == 422
