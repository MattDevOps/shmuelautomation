"""Site content CRUD and the public read side.

The behaviour worth protecting: slugs are public URLs, so a duplicate would
silently shadow a page; and unpublished content must never leak through the
public routes, since drafts are how Shmuel works on a post before it is ready.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.content_routes import slugify
from shmuel_backend.models import BlogPost, Neighborhood, SitePage


def test_slugify() -> None:
    assert slugify("Exploring Jerusalem on Two Wheels") == (
        "exploring-jerusalem-on-two-wheels"
    )
    assert slugify("  Rehavia & Talbiya!  ") == "rehavia-talbiya"
    # Hebrew is not transliterated, so it collapses to empty and the caller
    # must supply a slug explicitly.
    assert slugify("שכונת רחביה") == ""


def test_create_blog_derives_slug(client: TestClient) -> None:
    r = client.post("/content/blog", json={"title": "A Day in Baka"})
    assert r.status_code == 201
    assert r.json()["slug"] == "a-day-in-baka"


def test_hebrew_title_needs_explicit_slug(client: TestClient) -> None:
    r = client.post("/content/blog", json={"title": "שכונת רחביה"})
    assert r.status_code == 422

    ok = client.post(
        "/content/blog", json={"title": "שכונת רחביה", "slug": "rehavia-he"}
    )
    assert ok.status_code == 201
    assert ok.json()["slug"] == "rehavia-he"


def test_duplicate_slug_rejected(client: TestClient) -> None:
    client.post("/content/blog", json={"title": "A Day in Baka"})
    r = client.post("/content/blog", json={"title": "A Day in Baka"})
    assert r.status_code == 409


def test_update_to_taken_slug_rejected(client: TestClient) -> None:
    client.post("/content/blog", json={"title": "First Post"})
    second = client.post("/content/blog", json={"title": "Second Post"}).json()
    r = client.patch(f"/content/blog/{second['id']}", json={"slug": "first-post"})
    assert r.status_code == 409


def test_update_keeping_own_slug_is_fine(client: TestClient) -> None:
    """Re-saving a row without changing its slug must not collide with itself."""
    post = client.post("/content/blog", json={"title": "First Post"}).json()
    r = client.patch(
        f"/content/blog/{post['id']}", json={"slug": "first-post", "title": "Edited"}
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Edited"


@pytest.mark.asyncio
async def test_public_blog_hides_drafts(
    session: AsyncSession, client: TestClient
) -> None:
    session.add(BlogPost(slug="live", title="Live", published=True))
    session.add(BlogPost(slug="draft", title="Draft", published=False))
    await session.commit()

    slugs = [p["slug"] for p in client.get("/public/blog").json()]
    assert slugs == ["live"]

    assert client.get("/public/blog/draft").status_code == 404
    assert client.get("/public/blog/live").status_code == 200


@pytest.mark.asyncio
async def test_public_blog_is_cacheable(
    session: AsyncSession, client: TestClient
) -> None:
    session.add(BlogPost(slug="live", title="Live", published=True))
    await session.commit()
    r = client.get("/public/blog")
    assert r.headers["cache-control"] == "public, max-age=60"


@pytest.mark.asyncio
async def test_neighborhoods_sort_by_order_then_title(
    session: AsyncSession, client: TestClient
) -> None:
    session.add(Neighborhood(slug="c", title="Cee", sort_order=1))
    session.add(Neighborhood(slug="a", title="Ay", sort_order=0))
    session.add(Neighborhood(slug="b", title="Bee", sort_order=0))
    await session.commit()

    slugs = [n["slug"] for n in client.get("/content/neighborhoods").json()]
    assert slugs == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_public_neighborhood_hides_drafts(
    session: AsyncSession, client: TestClient
) -> None:
    session.add(Neighborhood(slug="baka", title="Baka", published=True))
    session.add(Neighborhood(slug="secret", title="Secret", published=False))
    await session.commit()

    slugs = [n["slug"] for n in client.get("/public/neighborhoods").json()]
    assert slugs == ["baka"]
    assert client.get("/public/neighborhoods/secret").status_code == 404


@pytest.mark.asyncio
async def test_page_keeps_acf_data(session: AsyncSession, client: TestClient) -> None:
    """Contact details ride in `data`; editing the body must not drop them."""
    session.add(
        SitePage(
            slug="contact",
            title="Contact",
            content_html="<p>old</p>",
            data={"contact_data": {"phone_number": "02-123", "email": "a@b.c"}},
        )
    )
    await session.commit()

    page = client.get("/content/pages").json()[0]
    r = client.patch(f"/content/pages/{page['id']}", json={"content_html": "<p>new</p>"})
    assert r.status_code == 200
    assert r.json()["content_html"] == "<p>new</p>"
    assert r.json()["data"]["contact_data"]["phone_number"] == "02-123"

    public = client.get("/public/pages/contact").json()
    assert public["data"]["contact_data"]["email"] == "a@b.c"


def test_delete_blog(client: TestClient) -> None:
    post = client.post("/content/blog", json={"title": "Temp"}).json()
    assert client.delete(f"/content/blog/{post['id']}").status_code == 204
    assert client.get("/content/blog").json() == []


def test_missing_row_404s(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.patch(f"/content/blog/{missing}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/content/blog/{missing}").status_code == 404
