from fastapi.testclient import TestClient

CSV_HEADER = "Phone,Name,Email,Language,Segments,Notes\n"


def _post_csv(
    client: TestClient, body: str, *, dry_run: bool = True
) -> dict[str, object]:
    files = {"file": ("contacts.csv", body.encode("utf-8"), "text/csv")}
    r = client.post(
        f"/contacts/import?dry_run={'true' if dry_run else 'false'}",
        files=files,
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_dry_run_previews_create_rows(client: TestClient) -> None:
    csv = (
        CSV_HEADER
        + "+972500000001,Yossi Cohen,yossi@example.com,he,buyer;baka,Notes here\n"
        + "+972500000002,Dani Levi,,he,renter,\n"
    )
    result = _post_csv(client, csv, dry_run=True)

    assert result["summary"]["total_rows"] == 2
    assert result["summary"]["would_create"] == 2
    assert result["summary"]["would_skip_duplicates"] == 0
    assert result["summary"]["errors"] == 0
    assert all(r["status"] == "create" for r in result["rows"])
    assert result["rows"][0]["segments"] == ["buyer", "baka"]


def test_dry_run_does_not_write_anything(client: TestClient) -> None:
    csv = CSV_HEADER + "+972500000001,Yossi Cohen,,,,\n"
    _post_csv(client, csv, dry_run=True)

    # No contacts should be visible afterward
    r = client.get("/contacts")
    assert r.json() == []


def test_apply_creates_contacts(client: TestClient) -> None:
    csv = (
        CSV_HEADER
        + "+972500000001,Yossi,yossi@example.com,he,buyer;baka,\n"
        + "+972500000002,Dani,,,renter,\n"
    )
    result = _post_csv(client, csv, dry_run=False)

    assert all(r["status"] == "created" for r in result["rows"])
    contacts = client.get("/contacts").json()
    by_name = {c["name"]: c for c in contacts}
    assert "Yossi" in by_name
    assert by_name["Yossi"]["segments"] == ["buyer", "baka"]
    assert by_name["Yossi"]["source"] == "csv-import"


def test_dedup_skips_existing_phones(client: TestClient) -> None:
    # Pre-create one contact
    client.post(
        "/contacts",
        json={"name": "Yossi", "phone": "+972500000001", "segments": ["buyer"]},
    )

    csv = (
        CSV_HEADER
        + "+972500000001,Yossi (dup),,,,\n"
        + "+972500000002,New Person,,,,\n"
    )
    result = _post_csv(client, csv, dry_run=True)

    assert result["summary"]["would_create"] == 1
    assert result["summary"]["would_skip_duplicates"] == 1
    statuses = {r["name"]: r["status"] for r in result["rows"]}
    assert statuses["Yossi (dup)"] == "duplicate"
    assert statuses["New Person"] == "create"


def test_dedup_handles_phone_formatting_differences(client: TestClient) -> None:
    client.post(
        "/contacts",
        json={"name": "Yossi", "phone": "+972500000001"},
    )
    csv = CSV_HEADER + "+972 50-000-0001,Yossi reformatted,,,,\n"
    result = _post_csv(client, csv, dry_run=True)
    assert result["rows"][0]["status"] == "duplicate"


def test_dedup_within_same_import_batch(client: TestClient) -> None:
    csv = (
        CSV_HEADER
        + "+972500000001,First,,,,\n"
        + "+972 50 0000001,Same number reformatted,,,,\n"
    )
    result = _post_csv(client, csv, dry_run=False)
    statuses = {r["name"]: r["status"] for r in result["rows"]}
    assert statuses["First"] == "created"
    assert statuses["Same number reformatted"] == "duplicate"
    # Only one contact actually created
    assert len(client.get("/contacts").json()) == 1


def test_missing_name_is_error(client: TestClient) -> None:
    csv = CSV_HEADER + "+972500000001,,no-name@example.com,,,\n"
    result = _post_csv(client, csv, dry_run=True)
    assert result["rows"][0]["status"] == "error"
    assert "name" in result["rows"][0]["detail"].lower()


def test_apply_skips_errors_and_duplicates_inserts_only_creates(
    client: TestClient,
) -> None:
    client.post("/contacts", json={"name": "existing", "phone": "+972000"})

    csv = (
        CSV_HEADER
        + "+972500000001,New A,,,,\n"
        + "+972999111,,,,,\n"  # error (blank name with a phone)
        + "+972000,duplicate of existing,,,,\n"  # dup
        + "+972500000002,New B,,,,\n"
    )
    result = _post_csv(client, csv, dry_run=False)
    assert result["summary"]["would_create"] == 2
    assert result["summary"]["would_skip_duplicates"] == 1
    assert result["summary"]["errors"] == 1

    names = {c["name"] for c in client.get("/contacts").json()}
    assert names == {"existing", "New A", "New B"}


def test_csv_supports_utf8_bom_and_hebrew(client: TestClient) -> None:
    body = "﻿" + CSV_HEADER + "+972500000001,דני לוי,,he,renter;rehavia,הערה\n"
    files = {"file": ("contacts.csv", body.encode("utf-8"), "text/csv")}
    r = client.post("/contacts/import?dry_run=false", files=files)
    assert r.status_code == 200
    assert r.json()["rows"][0]["name"] == "דני לוי"
    contacts = client.get("/contacts").json()
    assert contacts[0]["notes"] == "הערה"


def test_empty_file_rejected(client: TestClient) -> None:
    files = {"file": ("contacts.csv", b"", "text/csv")}
    r = client.post("/contacts/import?dry_run=true", files=files)
    assert r.status_code == 400


def test_empty_phone_always_creates(client: TestClient) -> None:
    csv = CSV_HEADER + ",No phone here,no@example.com,en,,\n"
    result = _post_csv(client, csv, dry_run=True)
    assert result["rows"][0]["status"] == "create"


def test_export_now_includes_segments_column(client: TestClient) -> None:
    client.post(
        "/contacts",
        json={
            "name": "Yossi",
            "phone": "+972500000001",
            "segments": ["buyer", "baka"],
        },
    )
    r = client.get("/contacts/export.csv")
    text = r.content.decode("utf-8-sig")
    assert "Segments" in text.splitlines()[0]
    assert "buyer;baka" in text
