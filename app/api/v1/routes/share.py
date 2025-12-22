from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Query
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.api.v1.models import (
    Sharer,
    StandardResponse,
    PaginatedMetadata,
)
from app.services import share_service

router = APIRouter(prefix="/sharing", tags=["Share"])


@router.post("/share")
async def sharing(
    blog_id: int,
    content: str | None = None,
    react_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await share_service.sharing(
        blog_id=blog_id, content=content, react_type=react_type, db=db, payload=payload
    )


@router.get(
    "/view_shares",
    response_model=StandardResponse[PaginatedMetadata[Sharer]],
    response_model_exclude_none=True,
)
async def views(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    session: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await share_service.views(
        session=session, payload=payload, page=page, limit=limit
    )


@router.get("/view_a_share", response_model=StandardResponse)
async def view_one(
    share_id: int,
    session: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await share_service.view(share_id=share_id, session=session, payload=payload)


@router.delete("/delete", response_model=StandardResponse)
async def delete_one(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await share_service.delete_one(share_id=share_id, db=db, payload=payload)
