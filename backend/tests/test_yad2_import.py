from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "yad2_listing.html"


@respx.mock
def test_imports_open_graph_and_json_ld_from_listing(client: TestClient) -> None:
    url = "https://www.yad2.co.il/realestate/item/abc123"
    respx.get(url).respond(text=FIXTURE.read_text(encoding="utf-8"))

    r = client.post("/properties/import/yad2", json={"url": url})
    assert r.status_code == 200
    body = r.json()

    assert body["url"] == url
    assert body["title"] and "בקעה" in body["title"]
    assert body["description"]
    assert body["price"] == "3200000"
    assert body["neighborhood"] == "Baka"
    assert body["address"] == "Emek Refaim 12"
    assert body["rooms"] == "4"
    assert body["size_sqm"] == 95
    assert body["image_urls"] == [
        "https://img.yad2.co.il/photo1.jpg",
        "https://img.yad2.co.il/photo2.jpg",
    ]
    assert body["warnings"] == []


def test_rejects_non_yad2_url(client: TestClient) -> None:
    r = client.post(
        "/properties/import/yad2", json={"url": "https://example.com/listing"}
    )
    assert r.status_code == 400


def test_accepts_subdomain_yad2_url(client: TestClient) -> None:
    url = "https://m.yad2.co.il/realestate/item/abc123"

    @respx.mock
    def call() -> None:
        respx.get(url).respond(text="<html></html>")
        r = client.post("/properties/import/yad2", json={"url": url})
        assert r.status_code == 200

    call()


@respx.mock
def test_returns_warnings_when_fetch_fails(client: TestClient) -> None:
    url = "https://www.yad2.co.il/realestate/item/timeout"
    respx.get(url).mock(side_effect=httpx.ConnectTimeout("timeout"))

    r = client.post("/properties/import/yad2", json={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body["warnings"]
    assert any("Could not load" in w for w in body["warnings"])


@respx.mock
def test_returns_warnings_when_yad2_returns_4xx(client: TestClient) -> None:
    url = "https://www.yad2.co.il/realestate/item/blocked"
    respx.get(url).respond(status_code=403, text="forbidden")

    r = client.post("/properties/import/yad2", json={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert any("Could not load" in w for w in body["warnings"])


@respx.mock
def test_returns_warnings_when_no_data_extracted(client: TestClient) -> None:
    url = "https://www.yad2.co.il/realestate/item/empty"
    respx.get(url).respond(text="<html><body>empty</body></html>")

    r = client.post("/properties/import/yad2", json={"url": url})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] is None
    assert any("manually" in w for w in body["warnings"])


def test_rejects_empty_url(client: TestClient) -> None:
    r = client.post("/properties/import/yad2", json={"url": ""})
    assert r.status_code == 422
