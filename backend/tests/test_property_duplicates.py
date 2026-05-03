from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "rent",
        "price": "8500.00",
        "neighborhood": "Baka",
        "address": "12 Emek Refaim",
    }
    base.update(overrides)
    r = client.post("/properties", json=base)
    assert r.status_code == 201, r.text
    return r.json()


def test_finds_exact_match(client: TestClient) -> None:
    existing = _create(client)
    r = client.get(
        "/properties/duplicates",
        params={"neighborhood": "Baka", "address": "12 Emek Refaim"},
    )
    assert r.status_code == 200
    matches = r.json()
    assert len(matches) == 1
    assert matches[0]["id"] == existing["id"]


def test_case_insensitive_and_whitespace_tolerant(client: TestClient) -> None:
    _create(client, neighborhood="Baka", address="12 Emek Refaim")
    r = client.get(
        "/properties/duplicates",
        params={"neighborhood": "BAKA", "address": "  12   emek   refaim  "},
    )
    assert len(r.json()) == 1


def test_substring_match_either_direction(client: TestClient) -> None:
    """'12 Emek Refaim' should warn about an existing '12 Emek Refaim St',
    and vice versa."""
    _create(client, address="12 Emek Refaim St")
    longer_finds_shorter = client.get(
        "/properties/duplicates",
        params={"neighborhood": "Baka", "address": "12 Emek Refaim"},
    ).json()
    assert len(longer_finds_shorter) == 1

    _create(client, address="9 Hillel")
    shorter_finds_longer = client.get(
        "/properties/duplicates",
        params={"neighborhood": "Baka", "address": "9 Hillel St, 2nd entrance"},
    ).json()
    assert len(shorter_finds_longer) == 1
    assert shorter_finds_longer[0]["address"] == "9 Hillel"


def test_different_neighborhood_is_not_a_match(client: TestClient) -> None:
    _create(client, neighborhood="Baka", address="12 Emek Refaim")
    r = client.get(
        "/properties/duplicates",
        params={"neighborhood": "Rehavia", "address": "12 Emek Refaim"},
    )
    assert r.json() == []


def test_exclude_id_skips_self(client: TestClient) -> None:
    """When editing an existing property, the property must not match itself."""
    p = _create(client)
    r = client.get(
        "/properties/duplicates",
        params={
            "neighborhood": "Baka",
            "address": "12 Emek Refaim",
            "exclude_id": p["id"],
        },
    )
    assert r.json() == []


def test_returns_slim_payload(client: TestClient) -> None:
    _create(client, type="sale", price="3200000", neighborhood="Baka", address="12 Emek Refaim")
    match = client.get(
        "/properties/duplicates",
        params={"neighborhood": "Baka", "address": "12 Emek Refaim"},
    ).json()[0]
    # Slim — no owner PII, notes, or broker terms in this response.
    assert set(match.keys()) == {
        "id",
        "type",
        "status",
        "price",
        "currency",
        "neighborhood",
        "address",
    }


def test_missing_required_query_params_rejected(client: TestClient) -> None:
    assert client.get("/properties/duplicates").status_code == 422
    assert (
        client.get("/properties/duplicates", params={"neighborhood": "Baka"}).status_code
        == 422
    )
