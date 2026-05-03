import time
import uuid

from fastapi.testclient import TestClient


def _create_property(client: TestClient) -> dict[str, object]:
    r = client.post(
        "/properties",
        json={"type": "rent", "price": "8000.00", "neighborhood": "Baka"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_then_list(client: TestClient) -> None:
    prop = _create_property(client)
    r = client.post(
        f"/properties/{prop['id']}/notes",
        json={"body": "Called landlord — available end of month"},
    )
    assert r.status_code == 201
    note = r.json()
    assert note["property_id"] == prop["id"]
    assert note["body"].startswith("Called landlord")

    listed = client.get(f"/properties/{prop['id']}/notes").json()
    assert len(listed) == 1
    assert listed[0]["id"] == note["id"]


def test_list_returns_newest_first(client: TestClient) -> None:
    prop = _create_property(client)
    first = client.post(
        f"/properties/{prop['id']}/notes", json={"body": "First"}
    ).json()
    # Tiny gap so created_at is strictly later — SQLite resolves to seconds
    # for CURRENT_TIMESTAMP without further config.
    time.sleep(1.05)
    second = client.post(
        f"/properties/{prop['id']}/notes", json={"body": "Second"}
    ).json()
    rows = client.get(f"/properties/{prop['id']}/notes").json()
    assert [r["id"] for r in rows] == [second["id"], first["id"]]


def test_create_rejects_blank_body(client: TestClient) -> None:
    prop = _create_property(client)
    r = client.post(
        f"/properties/{prop['id']}/notes", json={"body": ""}
    )
    assert r.status_code == 422


def test_create_rejects_too_long_body(client: TestClient) -> None:
    prop = _create_property(client)
    r = client.post(
        f"/properties/{prop['id']}/notes", json={"body": "x" * 5001}
    )
    assert r.status_code == 422


def test_404_when_property_missing(client: TestClient) -> None:
    fake = str(uuid.uuid4())
    assert client.get(f"/properties/{fake}/notes").status_code == 404
    assert (
        client.post(f"/properties/{fake}/notes", json={"body": "x"}).status_code
        == 404
    )


def test_delete_note(client: TestClient) -> None:
    prop = _create_property(client)
    note = client.post(
        f"/properties/{prop['id']}/notes", json={"body": "Will delete"}
    ).json()
    r = client.delete(f"/properties/{prop['id']}/notes/{note['id']}")
    assert r.status_code == 204
    assert client.get(f"/properties/{prop['id']}/notes").json() == []


def test_delete_note_404_when_missing_or_wrong_property(
    client: TestClient,
) -> None:
    prop_a = _create_property(client)
    prop_b = _create_property(client)
    note = client.post(
        f"/properties/{prop_a['id']}/notes", json={"body": "On A"}
    ).json()

    # Wrong property id
    r = client.delete(f"/properties/{prop_b['id']}/notes/{note['id']}")
    assert r.status_code == 404
    # Note still exists
    assert len(client.get(f"/properties/{prop_a['id']}/notes").json()) == 1


def test_notes_cascade_when_property_deleted(client: TestClient) -> None:
    """When a property is deleted, its notes go with it. We don't want
    orphan notes hanging around in the DB after Shmuel cleans up."""
    prop = _create_property(client)
    client.post(f"/properties/{prop['id']}/notes", json={"body": "n1"})
    client.post(f"/properties/{prop['id']}/notes", json={"body": "n2"})
    assert len(client.get(f"/properties/{prop['id']}/notes").json()) == 2

    client.delete(f"/properties/{prop['id']}")
    # Property is gone, list endpoint 404s.
    assert client.get(f"/properties/{prop['id']}/notes").status_code == 404


def test_notes_isolated_per_property(client: TestClient) -> None:
    a = _create_property(client)
    b = _create_property(client)
    client.post(f"/properties/{a['id']}/notes", json={"body": "for A"})
    client.post(f"/properties/{b['id']}/notes", json={"body": "for B"})
    assert client.get(f"/properties/{a['id']}/notes").json()[0]["body"] == "for A"
    assert client.get(f"/properties/{b['id']}/notes").json()[0]["body"] == "for B"
