from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> str:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "neighborhood": "Baka",
        "address": "12 Emek Refaim",
        "owner_name": "Yossi",
        "owner_phone": "+972500000000",
        "broker_fee_status": "yes",
        "broker_fee_amount": "8500",
        "notes": "haggle ok at 8200",
        "description": "Bright 3.5-room flat",
    }
    base.update(overrides)
    return str(client.post("/properties", json=base).json()["id"])


def test_public_list_omits_internal_fields(client: TestClient) -> None:
    _create(client)

    r = client.get("/public/properties")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]

    # Internal fields must not leak
    for forbidden in (
        "owner_name",
        "owner_phone",
        "broker_fee_status",
        "broker_fee_amount",
        "notes",
    ):
        assert forbidden not in item, (
            f"{forbidden} leaked into public payload: {item}"
        )

    # Public fields are present
    assert item["price"] == "8500.00"
    assert item["neighborhood"] == "Baka"
    assert item["address"] == "12 Emek Refaim"
    assert item["description"] == "Bright 3.5-room flat"
    assert item["photos"] == []


def test_public_list_hides_rented_and_sold_by_default(client: TestClient) -> None:
    _create(client, neighborhood="Baka")
    _create(client, neighborhood="Talpiot", status="rented")
    _create(client, neighborhood="Old Katamon", status="sold", type="sale")

    r = client.get("/public/properties")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["neighborhood"] == "Baka"


def test_public_list_filters_by_type_and_neighborhood(
    client: TestClient,
) -> None:
    _create(client, type="rent", neighborhood="Baka")
    _create(client, type="sale", neighborhood="Baka", price="2500000")
    _create(client, type="rent", neighborhood="Katamon")

    rentals = client.get("/public/properties", params={"type": "rent"}).json()
    assert rentals["total"] == 2

    baka = client.get(
        "/public/properties", params={"neighborhood": "Baka"}
    ).json()
    assert baka["total"] == 2

    rent_in_baka = client.get(
        "/public/properties", params={"type": "rent", "neighborhood": "Baka"}
    ).json()
    assert rent_in_baka["total"] == 1


def test_public_list_filters_by_price_range(client: TestClient) -> None:
    _create(client, price="5000")
    _create(client, price="10000")
    _create(client, price="20000")

    mid = client.get(
        "/public/properties", params={"min_price": "7000", "max_price": "15000"}
    ).json()
    assert mid["total"] == 1
    assert mid["items"][0]["price"] == "10000.00"


def test_public_list_paginates(client: TestClient) -> None:
    for i in range(5):
        _create(client, price=str(1000 + i))

    page1 = client.get(
        "/public/properties", params={"limit": 2, "offset": 0}
    ).json()
    page2 = client.get(
        "/public/properties", params={"limit": 2, "offset": 2}
    ).json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["limit"] == 2
    assert page1["offset"] == 0
    assert {p["id"] for p in page1["items"]}.isdisjoint(
        {p["id"] for p in page2["items"]}
    )


def test_public_list_sets_cache_control_header(client: TestClient) -> None:
    r = client.get("/public/properties")
    assert r.headers["cache-control"] == "public, max-age=60"


def test_public_get_returns_available_property(client: TestClient) -> None:
    pid = _create(client, neighborhood="Baka")

    r = client.get(f"/public/properties/{pid}")
    assert r.status_code == 200
    assert r.json()["neighborhood"] == "Baka"
    assert r.headers["cache-control"] == "public, max-age=60"


def test_public_get_404s_for_unavailable(client: TestClient) -> None:
    pid = _create(client, status="rented")
    r = client.get(f"/public/properties/{pid}")
    assert r.status_code == 404


def test_public_get_404s_for_missing(client: TestClient) -> None:
    r = client.get("/public/properties/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_limit_and_offset_validation(client: TestClient) -> None:
    assert client.get("/public/properties", params={"limit": 0}).status_code == 422
    assert client.get("/public/properties", params={"limit": 51}).status_code == 422
    assert client.get("/public/properties", params={"offset": -1}).status_code == 422


def test_public_list_does_not_leak_for_drafts(client: TestClient) -> None:
    """Even with non-default statuses, ?status= can't be passed to bypass the gate."""
    _create(client, status="rented")
    r = client.get("/public/properties", params={"status": "rented"})
    assert r.status_code == 200
    assert r.json()["total"] == 0  # The query param is ignored; default is 'available'
