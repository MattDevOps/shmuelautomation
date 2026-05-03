from fastapi.testclient import TestClient


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "rooms": "3.5",
        "size_sqm": 80,
        "neighborhood": "Baka",
        "owner_name": "Yossi",
        "owner_phone": "+972500000000",
        "broker_fee_status": "yes",
        "description": "Bright 3.5-room flat",
    }
    base.update(overrides)
    return base


def test_create_then_get(client: TestClient) -> None:
    r = client.post("/properties", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "rent"
    assert body["status"] == "available"
    assert body["currency"] == "ILS"
    assert body["city"] == "Jerusalem"

    got = client.get(f"/properties/{body['id']}")
    assert got.status_code == 200
    assert got.json()["neighborhood"] == "Baka"


def test_list_filters_by_type_and_status(client: TestClient) -> None:
    client.post("/properties", json=_payload(type="rent", price="8000"))
    client.post("/properties", json=_payload(type="sale", price="2500000"))
    client.post(
        "/properties", json=_payload(type="rent", price="9000", status="rented")
    )

    rentals = client.get("/properties", params={"type": "rent"}).json()
    assert len(rentals) == 2

    available_rentals = client.get(
        "/properties", params={"type": "rent", "status": "available"}
    ).json()
    assert len(available_rentals) == 1
    assert available_rentals[0]["price"] == "8000.00"


def test_list_filters_by_price_range(client: TestClient) -> None:
    client.post("/properties", json=_payload(price="5000"))
    client.post("/properties", json=_payload(price="10000"))
    client.post("/properties", json=_payload(price="15000"))

    mid = client.get(
        "/properties", params={"min_price": "7000", "max_price": "12000"}
    ).json()
    assert len(mid) == 1
    assert mid[0]["price"] == "10000.00"


def test_list_search_q_matches_address_and_description(client: TestClient) -> None:
    client.post("/properties", json=_payload(address="12 Emek Refaim", description="x"))
    client.post(
        "/properties", json=_payload(address="other", description="garden apartment")
    )
    client.post("/properties", json=_payload(address="other", description="x"))

    refaim = client.get("/properties", params={"q": "refaim"}).json()
    assert len(refaim) == 1

    garden = client.get("/properties", params={"q": "garden"}).json()
    assert len(garden) == 1


def test_patch_status(client: TestClient) -> None:
    created = client.post("/properties", json=_payload()).json()
    r = client.patch(f"/properties/{created['id']}", json={"status": "rented"})
    assert r.status_code == 200
    assert r.json()["status"] == "rented"


def test_patch_rejects_unknown_field(client: TestClient) -> None:
    created = client.post("/properties", json=_payload()).json()
    r = client.patch(f"/properties/{created['id']}", json={"bogus": "x"})
    assert r.status_code == 422


def test_delete(client: TestClient) -> None:
    created = client.post("/properties", json=_payload()).json()
    assert client.delete(f"/properties/{created['id']}").status_code == 204
    assert client.get(f"/properties/{created['id']}").status_code == 404


def test_get_missing_returns_404(client: TestClient) -> None:
    r = client.get("/properties/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_create_rejects_negative_price(client: TestClient) -> None:
    r = client.post("/properties", json=_payload(price="-100"))
    assert r.status_code == 422


def test_create_rejects_invalid_enum(client: TestClient) -> None:
    r = client.post("/properties", json=_payload(type="lease"))
    assert r.status_code == 422


def test_list_no_filters_returns_all(client: TestClient) -> None:
    client.post("/properties", json=_payload(neighborhood="Baka"))
    client.post("/properties", json=_payload(neighborhood="Katamon"))
    client.post("/properties", json=_payload(neighborhood="Rehavia"))

    rows = client.get("/properties").json()
    assert len(rows) == 3
    assert {r["neighborhood"] for r in rows} == {"Baka", "Katamon", "Rehavia"}


def test_list_filters_by_neighborhood(client: TestClient) -> None:
    client.post("/properties", json=_payload(neighborhood="Baka"))
    client.post("/properties", json=_payload(neighborhood="Katamon"))

    only_baka = client.get("/properties", params={"neighborhood": "Baka"}).json()
    assert len(only_baka) == 1
    assert only_baka[0]["neighborhood"] == "Baka"


def test_list_pagination(client: TestClient) -> None:
    for i in range(5):
        client.post("/properties", json=_payload(price=str(1000 + i)))

    page1 = client.get("/properties", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/properties", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2
    assert len(page2) == 2
    assert {p["id"] for p in page1}.isdisjoint({p["id"] for p in page2})


def test_patch_missing_returns_404(client: TestClient) -> None:
    r = client.patch(
        "/properties/00000000-0000-0000-0000-000000000000", json={"status": "rented"}
    )
    assert r.status_code == 404


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/properties/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
