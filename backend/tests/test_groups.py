from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "platform": "whatsapp",
        "audience": "rent",
        "name": "Jerusalem Rentals WA",
        "target_url": "https://chat.whatsapp.com/abc",
    }
    base.update(overrides)
    r = client.post("/groups", json=base)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_then_get(client: TestClient) -> None:
    g = _create(client)
    r = client.get(f"/groups/{g['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Jerusalem Rentals WA"
    assert r.json()["active"] is True


def test_create_rejects_blank_name(client: TestClient) -> None:
    r = client.post(
        "/groups",
        json={"platform": "whatsapp", "audience": "both", "name": ""},
    )
    assert r.status_code == 422


def test_list_filters_by_platform(client: TestClient) -> None:
    _create(client, platform="whatsapp", name="WA")
    _create(client, platform="facebook", name="FB")

    wa = client.get("/groups", params={"platform": "whatsapp"}).json()
    assert [g["name"] for g in wa] == ["WA"]
    fb = client.get("/groups", params={"platform": "facebook"}).json()
    assert [g["name"] for g in fb] == ["FB"]


def test_matches_property_type_includes_both_audience(
    client: TestClient,
) -> None:
    _create(client, audience="rent", name="Rent Only")
    _create(client, audience="sale", name="Sale Only")
    _create(client, audience="both", name="Universal")

    rent_groups = client.get(
        "/groups", params={"matches_property_type": "rent"}
    ).json()
    assert {g["name"] for g in rent_groups} == {"Rent Only", "Universal"}

    sale_groups = client.get(
        "/groups", params={"matches_property_type": "sale"}
    ).json()
    assert {g["name"] for g in sale_groups} == {"Sale Only", "Universal"}


def test_list_excludes_inactive_by_default(client: TestClient) -> None:
    g = _create(client, name="Disabled WA")
    client.patch(f"/groups/{g['id']}", json={"active": False})

    active_only = client.get("/groups").json()
    assert active_only == []

    all_groups = client.get("/groups", params={"active_only": False}).json()
    assert len(all_groups) == 1


def test_list_orders_by_platform_then_sort_order_then_name(
    client: TestClient,
) -> None:
    _create(client, platform="whatsapp", name="Z WA", sort_order=10)
    _create(client, platform="whatsapp", name="A WA", sort_order=20)
    _create(client, platform="facebook", name="FB X", sort_order=0)

    rows = client.get("/groups").json()
    # facebook < whatsapp alphabetically; within whatsapp, sort_order asc.
    assert [g["name"] for g in rows] == ["FB X", "Z WA", "A WA"]


def test_patch_renames_group(client: TestClient) -> None:
    g = _create(client, name="Old name")
    r = client.patch(f"/groups/{g['id']}", json={"name": "New name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New name"


def test_patch_rejects_unknown_field(client: TestClient) -> None:
    g = _create(client)
    r = client.patch(f"/groups/{g['id']}", json={"bogus": "x"})
    assert r.status_code == 422


def test_delete(client: TestClient) -> None:
    g = _create(client)
    assert client.delete(f"/groups/{g['id']}").status_code == 204
    assert client.get(f"/groups/{g['id']}").status_code == 404


def test_get_404(client: TestClient) -> None:
    r = client.get("/groups/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
