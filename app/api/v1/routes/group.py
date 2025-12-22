from fastapi import APIRouter, Depends, Query, Form, File, UploadFile
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.models import (
    StandardResponse,
    PaginatedMetadata,
    MemberResponse,
    GroupResponse,
)
from app.services import group_service


router = APIRouter(prefix="/group", tags=["Communities"])


@router.get("/group_access")
async def access(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.access(group_id=group_id, db=db, payload=payload)


@router.post("/groups")
async def create_group(
    profile_picture: UploadFile | None = File(None),
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.grouping(
        db=db, payload=payload, profile_picture=profile_picture, name=name
    )


@router.put("/edit_group")
async def edit_group(
    group_id: int,
    name: str | None = None,
    profile_picture: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.edit_group(
        db=db,
        payload=payload,
        group_id=group_id,
        name=name,
        profile_picture=profile_picture,
    )


@router.post("/add_admin")
async def add_admin(
    group_id: int,
    username: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.add_admin(
        db=db, payload=payload, group_id=group_id, username=username
    )


@router.post("/members")
async def add_member(
    group_id: int,
    username: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.add_member(
        db=db, payload=payload, group_id=group_id, username=username
    )


@router.get("/view_group_admins")
async def admins_list(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.admins_list(db=db, payload=payload, group_id=group_id)


@router.get(
    "/view_members", response_model=StandardResponse[PaginatedMetadata[MemberResponse]]
)
async def members_list(
    group_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.members_list(
        db=db, payload=payload, group_id=group_id, page=page, limit=limit
    )


@router.get(
    "/view_groups", response_model=StandardResponse[PaginatedMetadata[GroupResponse]]
)
async def groups_list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.groups_list(
        db=db, payload=payload, page=page, limit=limit
    )


@router.delete("/member_out")
async def delete_member(
    group_id: int,
    username: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await group_service.delete_member(
        db=db, payload=payload, group_id=group_id, username=username
    )
