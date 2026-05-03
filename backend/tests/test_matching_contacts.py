from fastapi.testclient import TestClient


def _create_sale_in_baka(client: TestClient) -> str:
    return str(
        client.post(
            "/properties",
            json={"type": "sale", "price": "3200000", "neighborhood": "Baka"},
        ).json()["id"]
    )


def _create_rent_in_rehavia(client: TestClient) -> str:
    return str(
        client.post(
            "/properties",
            json={"type": "rent", "price": "8500", "neighborhood": "Rehavia"},
        ).json()["id"]
    )


def _seed_contacts(client: TestClient) -> None:
    client.post(
        "/contacts",
        json={"name": "Buyer-Baka", "segments": ["buyer", "baka"]},
    )
    client.post("/contacts", json={"name": "Buyer-only", "segments": ["buyer"]})
    client.post("/contacts", json={"name": "Baka-only", "segments": ["baka"]})
    client.post(
        "/contacts", json={"name": "Renter-Rehavia", "segments": ["renter", "rehavia"]}
    )
    client.post(
        "/contacts",
        json={"name": "Landlord", "segments": ["landlord", "vip"]},
    )


def test_sale_in_baka_matches_buyers_and_baka_segment(
    client: TestClient,
) -> None:
    pid = _create_sale_in_baka(client)
    _seed_contacts(client)

    matches = client.get(f"/properties/{pid}/matching-contacts").json()
    by_name = {m["name"]: m for m in matches}

    # Three contacts match (Buyer-Baka, Buyer-only, Baka-only)
    assert set(by_name.keys()) == {"Buyer-Baka", "Buyer-only", "Baka-only"}
    # Buyer-Baka scored 2, others scored 1
    assert by_name["Buyer-Baka"]["match_score"] == 2
    assert set(by_name["Buyer-Baka"]["match_reasons"]) == {"buyer", "Baka"}
    assert by_name["Buyer-only"]["match_score"] == 1
    assert by_name["Baka-only"]["match_score"] == 1


def test_results_are_sorted_by_score_desc_then_name(client: TestClient) -> None:
    pid = _create_sale_in_baka(client)
    _seed_contacts(client)

    matches = client.get(f"/properties/{pid}/matching-contacts").json()
    # First result is the score-2 contact; rest sorted alphabetically
    assert matches[0]["name"] == "Buyer-Baka"
    assert matches[1]["name"] == "Baka-only"  # B comes before Buyer-only
    assert matches[2]["name"] == "Buyer-only"


def test_rent_uses_renter_audience(client: TestClient) -> None:
    pid = _create_rent_in_rehavia(client)
    _seed_contacts(client)

    matches = client.get(f"/properties/{pid}/matching-contacts").json()
    by_name = {m["name"]: m for m in matches}

    assert "Renter-Rehavia" in by_name
    assert by_name["Renter-Rehavia"]["match_score"] == 2
    # 'buyer' segment shouldn't match a rent property
    assert "Buyer-only" not in by_name


def test_no_matches_returns_empty_list(client: TestClient) -> None:
    pid = _create_sale_in_baka(client)
    # Seed only contacts that won't match
    client.post(
        "/contacts", json={"name": "Far away", "segments": ["renter", "telaviv"]}
    )

    r = client.get(f"/properties/{pid}/matching-contacts")
    assert r.status_code == 200
    assert r.json() == []


def test_404_for_unknown_property(client: TestClient) -> None:
    r = client.get(
        "/properties/00000000-0000-0000-0000-000000000000/matching-contacts"
    )
    assert r.status_code == 404


def test_segment_match_is_case_insensitive(client: TestClient) -> None:
    pid = _create_sale_in_baka(client)
    client.post(
        "/contacts",
        json={"name": "MixedCase", "segments": ["Buyer", "BAKA"]},
    )

    matches = client.get(f"/properties/{pid}/matching-contacts").json()
    by_name = {m["name"]: m for m in matches}
    assert by_name["MixedCase"]["match_score"] == 2
