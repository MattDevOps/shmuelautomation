"""Admin CRUD for site content, and the public read side.

Three content types mirrored out of WordPress — blog posts, neighbourhood
guides, and the static marketing pages. Shmuel edits them here so that
retiring WordPress does not mean handing his content to a developer.

Two routers:
- `admin_router` at `/content/*` — full CRUD behind the API key.
- `public_router` at `/public/*` — published rows only, cached, for the site.

The public routes exist now but the site does not call them yet; it keeps
reading WordPress until the per-type toggles are flipped. That is what makes
this safe to ship: everything is in place and inert.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.models import BlogPost, Neighborhood, SitePage

admin_router = APIRouter(prefix="/content", tags=["content"])
public_router = APIRouter(prefix="/public", tags=["public"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

CACHE_HEADER = "public, max-age=60"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A URL slug from a title. Ascii-only, so Hebrew titles need an explicit slug."""
    return _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")


# --------------------------------------------------------------- schemas


class BlogPostBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content_html: str = ""
    excerpt_html: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    published: bool = True


class BlogPostCreate(BlogPostBase):
    # Optional so the admin can just type a title; derived when omitted.
    slug: str | None = None


class BlogPostUpdate(BaseModel):
    slug: str | None = None
    title: str | None = None
    content_html: str | None = None
    excerpt_html: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    published: bool | None = None


class BlogPostRead(BlogPostBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    wp_id: int | None
    created_at: datetime
    updated_at: datetime


class NeighborhoodBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content_html: str = ""
    card_image_url: str | None = None
    hero_image_url: str | None = None
    sort_order: int = 0
    published: bool = True


class NeighborhoodCreate(NeighborhoodBase):
    slug: str | None = None


class NeighborhoodUpdate(BaseModel):
    slug: str | None = None
    title: str | None = None
    content_html: str | None = None
    card_image_url: str | None = None
    hero_image_url: str | None = None
    sort_order: int | None = None
    published: bool | None = None


class NeighborhoodRead(NeighborhoodBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    wp_id: int | None
    created_at: datetime
    updated_at: datetime


class SitePageBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content_html: str = ""
    data: dict[str, Any] | None = None
    published: bool = True


class SitePageCreate(SitePageBase):
    slug: str


class SitePageUpdate(BaseModel):
    title: str | None = None
    content_html: str | None = None
    data: dict[str, Any] | None = None
    published: bool | None = None


class SitePageRead(SitePageBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    wp_id: int | None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------- helpers


async def _get_or_404[M](
    session: AsyncSession, model: type[M], row_id: uuid.UUID
) -> M:
    row = await session.get(model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


async def _assert_slug_free(
    session: AsyncSession,
    model: Any,
    slug: str,
    *,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Slugs are the public URL, so a clash would silently shadow a page."""
    stmt = select(model.id).where(model.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(model.id != exclude_id)
    if (await session.execute(stmt)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"slug '{slug}' is already used",
        )


def _resolve_slug(explicit: str | None, title: str) -> str:
    slug = (explicit or "").strip() or slugify(title)
    if not slug:
        raise HTTPException(
            status_code=422,
            detail="could not derive a slug from the title; provide one explicitly",
        )
    return slug


# --------------------------------------------------------------- blog (admin)


@admin_router.get("/blog", response_model=list[BlogPostRead])
async def list_blog(
    session: SessionDep,
    published_only: Annotated[bool, Query()] = False,
) -> list[BlogPost]:
    stmt = select(BlogPost)
    if published_only:
        stmt = stmt.where(BlogPost.published.is_(True))
    stmt = stmt.order_by(BlogPost.published_at.desc().nullslast())
    return list((await session.execute(stmt)).scalars().all())


@admin_router.post("/blog", response_model=BlogPostRead, status_code=201)
async def create_blog(payload: BlogPostCreate, session: SessionDep) -> BlogPost:
    slug = _resolve_slug(payload.slug, payload.title)
    await _assert_slug_free(session, BlogPost, slug)
    row = BlogPost(**payload.model_dump(exclude={"slug"}), slug=slug)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@admin_router.patch("/blog/{row_id}", response_model=BlogPostRead)
async def update_blog(
    row_id: uuid.UUID, payload: BlogPostUpdate, session: SessionDep
) -> BlogPost:
    row = await _get_or_404(session, BlogPost, row_id)
    changes = payload.model_dump(exclude_unset=True)
    if "slug" in changes and changes["slug"]:
        await _assert_slug_free(session, BlogPost, changes["slug"], exclude_id=row_id)
    for field, value in changes.items():
        if value is not None or field in {"excerpt_html", "image_url", "published_at"}:
            setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return row


@admin_router.delete("/blog/{row_id}", status_code=204)
async def delete_blog(row_id: uuid.UUID, session: SessionDep) -> Response:
    row = await _get_or_404(session, BlogPost, row_id)
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


# ------------------------------------------------------- neighborhoods (admin)


@admin_router.get("/neighborhoods", response_model=list[NeighborhoodRead])
async def list_neighborhoods(session: SessionDep) -> list[Neighborhood]:
    stmt = select(Neighborhood).order_by(Neighborhood.sort_order, Neighborhood.title)
    return list((await session.execute(stmt)).scalars().all())


@admin_router.post("/neighborhoods", response_model=NeighborhoodRead, status_code=201)
async def create_neighborhood(
    payload: NeighborhoodCreate, session: SessionDep
) -> Neighborhood:
    slug = _resolve_slug(payload.slug, payload.title)
    await _assert_slug_free(session, Neighborhood, slug)
    row = Neighborhood(**payload.model_dump(exclude={"slug"}), slug=slug)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@admin_router.patch("/neighborhoods/{row_id}", response_model=NeighborhoodRead)
async def update_neighborhood(
    row_id: uuid.UUID, payload: NeighborhoodUpdate, session: SessionDep
) -> Neighborhood:
    row = await _get_or_404(session, Neighborhood, row_id)
    changes = payload.model_dump(exclude_unset=True)
    if "slug" in changes and changes["slug"]:
        await _assert_slug_free(
            session, Neighborhood, changes["slug"], exclude_id=row_id
        )
    for field, value in changes.items():
        if value is not None or field in {"card_image_url", "hero_image_url"}:
            setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return row


@admin_router.delete("/neighborhoods/{row_id}", status_code=204)
async def delete_neighborhood(row_id: uuid.UUID, session: SessionDep) -> Response:
    row = await _get_or_404(session, Neighborhood, row_id)
    await session.delete(row)
    await session.commit()
    return Response(status_code=204)


# --------------------------------------------------------------- pages (admin)


@admin_router.get("/pages", response_model=list[SitePageRead])
async def list_pages(session: SessionDep) -> list[SitePage]:
    return list(
        (await session.execute(select(SitePage).order_by(SitePage.slug)))
        .scalars()
        .all()
    )


@admin_router.post("/pages", response_model=SitePageRead, status_code=201)
async def create_page(payload: SitePageCreate, session: SessionDep) -> SitePage:
    await _assert_slug_free(session, SitePage, payload.slug)
    row = SitePage(**payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@admin_router.patch("/pages/{row_id}", response_model=SitePageRead)
async def update_page(
    row_id: uuid.UUID, payload: SitePageUpdate, session: SessionDep
) -> SitePage:
    row = await _get_or_404(session, SitePage, row_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None or field == "data":
            setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return row


# --------------------------------------------------------------- public reads


@public_router.get("/blog", response_model=list[BlogPostRead])
async def public_blog(session: SessionDep, response: Response) -> list[BlogPost]:
    response.headers["cache-control"] = CACHE_HEADER
    stmt = (
        select(BlogPost)
        .where(BlogPost.published.is_(True))
        .order_by(BlogPost.published_at.desc().nullslast())
    )
    return list((await session.execute(stmt)).scalars().all())


@public_router.get("/blog/{slug}", response_model=BlogPostRead)
async def public_blog_post(
    slug: str, session: SessionDep, response: Response
) -> BlogPost:
    response.headers["cache-control"] = CACHE_HEADER
    row = (
        await session.execute(
            select(BlogPost).where(
                BlogPost.slug == slug, BlogPost.published.is_(True)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@public_router.get("/neighborhoods", response_model=list[NeighborhoodRead])
async def public_neighborhoods(
    session: SessionDep, response: Response
) -> list[Neighborhood]:
    response.headers["cache-control"] = CACHE_HEADER
    stmt = (
        select(Neighborhood)
        .where(Neighborhood.published.is_(True))
        .order_by(Neighborhood.sort_order, Neighborhood.title)
    )
    return list((await session.execute(stmt)).scalars().all())


@public_router.get("/neighborhoods/{slug}", response_model=NeighborhoodRead)
async def public_neighborhood(
    slug: str, session: SessionDep, response: Response
) -> Neighborhood:
    response.headers["cache-control"] = CACHE_HEADER
    row = (
        await session.execute(
            select(Neighborhood).where(
                Neighborhood.slug == slug, Neighborhood.published.is_(True)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


@public_router.get("/pages/{slug}", response_model=SitePageRead)
async def public_page(slug: str, session: SessionDep, response: Response) -> SitePage:
    response.headers["cache-control"] = CACHE_HEADER
    row = (
        await session.execute(
            select(SitePage).where(
                SitePage.slug == slug, SitePage.published.is_(True)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row
