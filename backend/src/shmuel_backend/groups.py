"""Configurable destinations for property posts.

Shmuel curates this list from the admin: WhatsApp groups, FB groups, his
WhatsApp Status, Janglo, anything else. Each group is tagged with platform
+ audience (rent/sale/both) so the share modal can suggest only the
relevant ones for a given property.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shmuel_backend.db import get_session
from shmuel_backend.enums import GroupAudience, GroupPlatform
from shmuel_backend.models import Group
from shmuel_backend.schemas import GroupCreate, GroupRead, GroupUpdate

router = APIRouter(prefix="/groups", tags=["groups"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[GroupRead])
async def list_groups(
    session: SessionDep,
    platform: GroupPlatform | None = None,
    audience: GroupAudience | None = None,
    matches_property_type: Annotated[
        str | None,
        Query(
            description=(
                "If 'rent' or 'sale', returns groups whose audience matches "
                "(plus 'both'-audience groups). Use this from the share UI."
            ),
        ),
    ] = None,
    active_only: bool = True,
) -> list[Group]:
    stmt = select(Group)
    if active_only:
        stmt = stmt.where(Group.active.is_(True))
    if platform is not None:
        stmt = stmt.where(Group.platform == platform)
    if audience is not None:
        stmt = stmt.where(Group.audience == audience)
    if matches_property_type in ("rent", "sale"):
        stmt = stmt.where(
            Group.audience.in_([matches_property_type, GroupAudience.BOTH])
        )
    stmt = stmt.order_by(Group.platform, Group.sort_order, Group.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(payload: GroupCreate, session: SessionDep) -> Group:
    group = Group(**payload.model_dump())
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


@router.get("/{group_id}", response_model=GroupRead)
async def get_group(group_id: uuid.UUID, session: SessionDep) -> Group:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


@router.patch("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: uuid.UUID, payload: GroupUpdate, session: SessionDep
) -> Group:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await session.commit()
    await session.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: uuid.UUID, session: SessionDep) -> Response:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    await session.delete(group)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
