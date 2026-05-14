"""Tests for the content-translation service.

Covers extraction, hash-based skip, upsert, the public lookup endpoint,
and the OpenAI no-op path. The OpenAI HTTP call is stubbed via respx so
no real network access is needed.
"""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from shmuel_backend.translations import (
    _extract_blog_fields,
    _extract_neighborhood_fields,
    _extract_property_fields,
    _hash_source,
    sync_translations,
)


def test_extract_property_fields_only_includes_translatable() -> None:
    prop = {
        "title": {"rendered": "Beautiful Apartment / Luxury"},
        "acf": {
            "details_properties": {
                "property_name": "Beautiful Apartment",
                "neighborhood": "Talbiye",
                "street_name": "Disraeli",
                "price_shekels": "5500000",
                "beds": "4",
            },
            "description": {
                "paragraph_1": "Experience the pinnacle of luxury.",
                "paragraph_2": "Spacious living with two master bedrooms.",
            },
            "more_information": ["Private parking", "Storage room", ""],
        },
    }
    fields = _extract_property_fields(prop)
    # Translatable fields present:
    assert "title" in fields
    assert fields["property_name"] == "Beautiful Apartment"
    assert "description_p1" in fields
    assert "description_p2" in fields
    assert fields["more_info_0"] == "Private parking"
    assert fields["more_info_1"] == "Storage room"
    # Empty more_info entries are skipped:
    assert "more_info_2" not in fields
    # Proper nouns and numbers are NOT extracted:
    assert "neighborhood" not in fields
    assert "street_name" not in fields
    assert "price_shekels" not in fields
    assert "beds" not in fields


def test_extract_blog_fields() -> None:
    post = {
        "title": {"rendered": "Exploring Jerusalem on Two Wheels"},
        "excerpt": {"rendered": "<p>City cycling tips...</p>"},
        "content": {"rendered": "<p>Long-form post body.</p>"},
    }
    fields = _extract_blog_fields(post)
    assert fields["title"] == "Exploring Jerusalem on Two Wheels"
    assert "<p>" in fields["excerpt"]  # raw HTML preserved for translation
    assert "<p>" in fields["content"]


def test_extract_neighborhood_skips_title_proper_noun() -> None:
    n = {
        "title": {"rendered": "Yemin Moshe"},
        "content": {"rendered": "<p>A historic retreat...</p>"},
    }
    fields = _extract_neighborhood_fields(n)
    # Title is a proper noun, not translated:
    assert "title" not in fields
    assert "content" in fields


def test_hash_source_stable_across_whitespace_in_html() -> None:
    # _hash_source is called after _strip_html, so two markup variants of
    # the same text should still produce the same hash via the strip pre-pass.
    from shmuel_backend.translations import _strip_html
    a = _strip_html("<p>Hello world</p>")
    b = _strip_html("<div>Hello world</div>")
    assert _hash_source(a) == _hash_source(b)


@pytest.mark.asyncio
async def test_sync_noop_when_no_api_key(session, monkeypatch) -> None:
    """With OPENAI_API_KEY unset, the translate() client returns None and
    sync counts the attempts as errors but never writes to the DB."""
    from shmuel_backend.config import settings as cfg
    monkeypatch.setattr(cfg, "openai_api_key", "")
    with respx.mock(assert_all_called=False) as rmock:
        # Stub WP REST to return one property, one blog, one neighborhood.
        for path, slug in [
            ("/properties", "p-1-test"),
            ("/blog", "blog-1-test"),
            ("/neighborhood", "n-1-test"),
        ]:
            rmock.get(url__startswith=f"{cfg.wp_rest_base}{path}").mock(
                return_value=Response(
                    200,
                    json=[
                        {
                            "slug": slug,
                            "title": {"rendered": "Source title"},
                            "acf": {"description": {"paragraph_1": "Short body."}},
                            "content": {"rendered": "<p>Body</p>"},
                            "excerpt": {"rendered": "<p>Ex</p>"},
                        }
                    ],
                )
            )
        result = await sync_translations(session)
    assert result.total_translated == 0
    # All translation attempts return None → counted as errors, no rows written.
    assert any(s.errors > 0 for s in result.per_type)


@pytest.mark.asyncio
async def test_sync_writes_translations_on_first_run(session, monkeypatch) -> None:
    """With a stubbed OpenAI returning a fixed translation, sync should
    write rows for each (field × target_lang) and return non-zero counts."""
    from shmuel_backend.config import settings as cfg
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")
    with respx.mock(assert_all_called=False) as rmock:
        # One property, blog, neighborhood each.
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/properties").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "slug": "p-1-test",
                        "title": {"rendered": "Source title"},
                        "acf": {
                            "details_properties": {"property_name": "Source title"},
                            "description": {"paragraph_1": "Short body."},
                        },
                    }
                ],
            )
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/blog").mock(
            return_value=Response(200, json=[])
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/neighborhood").mock(
            return_value=Response(200, json=[])
        )
        # Stub OpenAI chat completion.
        rmock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "TRANSLATED"}}]},
            )
        )
        result = await sync_translations(session)
    # 1 property × 3 fields (title, property_name, description_p1) × 3 langs = 9 rows.
    assert result.total_translated == 9

    # Second run with same content should fully skip — same hash.
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/properties").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "slug": "p-1-test",
                        "title": {"rendered": "Source title"},
                        "acf": {
                            "details_properties": {"property_name": "Source title"},
                            "description": {"paragraph_1": "Short body."},
                        },
                    }
                ],
            )
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/blog").mock(
            return_value=Response(200, json=[])
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/neighborhood").mock(
            return_value=Response(200, json=[])
        )
        # No OpenAI mock — sync should not call it on idempotent re-run.
        result2 = await sync_translations(session)
    assert result2.total_translated == 0
    property_stats = next(s for s in result2.per_type if s.content_type == "property")
    assert property_stats.skipped == 9


@pytest.mark.asyncio
async def test_public_translations_endpoint(client, session, monkeypatch) -> None:
    """GET /public/translations returns the stored translations for the
    requested slugs in the requested lang; missing items return empty fields."""
    from shmuel_backend.config import settings as cfg
    monkeypatch.setattr(cfg, "openai_api_key", "sk-test")
    with respx.mock(assert_all_called=False) as rmock:
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/properties").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "slug": "p-aaa",
                        "title": {"rendered": "AAA"},
                        "acf": {"description": {"paragraph_1": "Body aaa."}},
                    }
                ],
            )
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/blog").mock(
            return_value=Response(200, json=[])
        )
        rmock.get(url__startswith=f"{cfg.wp_rest_base}/neighborhood").mock(
            return_value=Response(200, json=[])
        )
        rmock.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={"choices": [{"message": {"content": "MOCK-HE"}}]},
            )
        )
        await sync_translations(session)

    # Lookup with one known slug + one missing slug.
    resp = client.get(
        "/public/translations",
        params={"content_type": "property", "slugs": "p-aaa,p-missing", "lang": "he"},
    )
    assert resp.status_code == 200
    bundles = resp.json()
    assert len(bundles) == 2
    by_slug = {b["content_slug"]: b for b in bundles}
    assert by_slug["p-aaa"]["fields"]["title"] == "MOCK-HE"
    assert by_slug["p-aaa"]["fields"]["description_p1"] == "MOCK-HE"
    assert by_slug["p-missing"]["fields"] == {}


def test_public_translations_rejects_invalid_lang(client) -> None:
    resp = client.get(
        "/public/translations",
        params={"content_type": "property", "slugs": "p-aaa", "lang": "de"},
    )
    assert resp.status_code == 422


def test_public_translations_rejects_invalid_content_type(client) -> None:
    resp = client.get(
        "/public/translations",
        params={"content_type": "page", "slugs": "p-aaa", "lang": "he"},
    )
    assert resp.status_code == 422
