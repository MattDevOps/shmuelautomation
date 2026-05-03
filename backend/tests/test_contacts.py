import csv
import io

from fastapi.testclient import TestClient


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Yossi Cohen",
        "phone": "+972500000000",
        "email": "yossi@example.com",
        "language": "he",
        "segments": ["buyer"],
        "notes": "Looking in Baka, budget 3.2M",
        "source": "manual",
    }
    base.update(overrides)
    r = client.post("/contacts", json=base)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_then_get(client: TestClient) -> None:
    created = _create(client)
    r = client.get(f"/contacts/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Yossi Cohen"
    assert r.json()["segments"] == ["buyer"]


def test_create_rejects_blank_name(client: TestClient) -> None:
    r = client.post("/contacts", json={"name": "", "segments": []})
    assert r.status_code == 422


def test_list_filters_by_segment_any_of(client: TestClient) -> None:
    _create(client, name="Buyer A", segments=["buyer"])
    _create(client, name="Renter B", segments=["renter"])
    _create(client, name="VIP Buyer C", segments=["buyer", "vip"])
    _create(client, name="Landlord D", segments=["landlord"])

    only_buyer = client.get(
        "/contacts", params={"segment": "buyer"}
    ).json()
    assert {c["name"] for c in only_buyer} == {"Buyer A", "VIP Buyer C"}

    buyer_or_renter = client.get(
        "/contacts", params=[("segment", "buyer"), ("segment", "renter")]
    ).json()
    assert {c["name"] for c in buyer_or_renter} == {
        "Buyer A",
        "Renter B",
        "VIP Buyer C",
    }


def test_list_search_q_matches_name_or_phone(client: TestClient) -> None:
    _create(client, name="Aviv Levi", phone="+972501111111")
    _create(client, name="Dani Cohen", phone="+972502222222")

    by_name = client.get("/contacts", params={"q": "aviv"}).json()
    assert len(by_name) == 1
    assert by_name[0]["name"] == "Aviv Levi"

    by_phone = client.get("/contacts", params={"q": "0500222"}).json()
    # The phone is searched literally; "+972502222222" doesn't include "0500222"
    assert len(by_phone) == 0

    by_phone_real = client.get("/contacts", params={"q": "97250222"}).json()
    assert len(by_phone_real) == 1


def test_segments_endpoint_returns_distinct_sorted(client: TestClient) -> None:
    _create(client, segments=["buyer", "vip"])
    _create(client, segments=["renter"])
    _create(client, segments=["buyer", "rehavia"])

    r = client.get("/contacts/segments")
    assert r.status_code == 200
    assert r.json() == ["buyer", "rehavia", "renter", "vip"]


def test_patch_segments(client: TestClient) -> None:
    created = _create(client, segments=["buyer"])
    r = client.patch(
        f"/contacts/{created['id']}",
        json={"segments": ["buyer", "vip", "rehavia"]},
    )
    assert r.status_code == 200
    assert set(r.json()["segments"]) == {"buyer", "vip", "rehavia"}


def test_patch_rejects_unknown_field(client: TestClient) -> None:
    created = _create(client)
    r = client.patch(f"/contacts/{created['id']}", json={"unknown": "x"})
    assert r.status_code == 422


def test_delete(client: TestClient) -> None:
    created = _create(client)
    assert client.delete(f"/contacts/{created['id']}").status_code == 204
    assert client.get(f"/contacts/{created['id']}").status_code == 404


def test_export_csv_format(client: TestClient) -> None:
    _create(
        client,
        name="Yossi",
        phone="+972500000000",
        email="y@example.com",
        language="he",
        notes="Multi-line\nnote here",
    )
    _create(
        client,
        name="Hebrew name דני",
        phone="+972511111111",
        notes='Includes "quotes" and commas, like this',
    )

    r = client.get("/contacts/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert (
        r.headers["content-disposition"].startswith('attachment; filename="contacts-')
    )

    text = r.content.decode("utf-8-sig")  # strip BOM
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["Phone", "Name", "Email", "Language", "Notes"]
    assert len(rows) == 3  # header + two contacts

    by_name = {r[1]: r for r in rows[1:]}
    assert by_name["Yossi"][2] == "y@example.com"
    assert "\n" not in by_name["Yossi"][4], "Newlines must be flattened"
    assert by_name["Hebrew name דני"][0] == "+972511111111"
    assert "quotes" in by_name["Hebrew name דני"][4]


def test_export_csv_starts_with_utf8_bom(client: TestClient) -> None:
    _create(client, name="Yossi")
    r = client.get("/contacts/export.csv")
    assert r.content.startswith(b"\xef\xbb\xbf"), (
        "Excel + webot need a BOM to render Hebrew correctly"
    )


def test_export_csv_filename_includes_segment_slug(client: TestClient) -> None:
    _create(client, segments=["buyer"])
    r = client.get("/contacts/export.csv", params={"segment": "buyer"})
    assert "contacts-buyer-" in r.headers["content-disposition"]


def test_export_csv_segment_filter(client: TestClient) -> None:
    _create(client, name="Buyer A", segments=["buyer"])
    _create(client, name="Renter B", segments=["renter"])

    r = client.get("/contacts/export.csv", params={"segment": "buyer"})
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 2  # header + 1
    assert rows[1][1] == "Buyer A"


def test_get_404(client: TestClient) -> None:
    r = client.get("/contacts/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_pagination(client: TestClient) -> None:
    for i in range(5):
        _create(client, name=f"Contact {i}", phone=f"+97250{i}")

    page1 = client.get("/contacts", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/contacts", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2
    assert len(page2) == 2
    assert {c["id"] for c in page1}.isdisjoint({c["id"] for c in page2})
