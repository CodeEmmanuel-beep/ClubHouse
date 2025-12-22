from fastapi import APIRouter, Depends, Query
from app.api.v1.models import (
    StandardResponse,
    CommentResponse,
    PaginatedMetadata,
    Commenter,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.services import comment_service
import tracemalloc

tracemalloc.start()

router = APIRouter(prefix="/comment", tags=["Comments"])


@router.post(
    "/comments",
    response_model=StandardResponse,
    response_model_exclude_none=True,
)
async def comment(
    comment: CommentResponse,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.c_express(comment=comment, db=db, payload=payload)


@router.get(
    "/view_comments",
    response_model=StandardResponse[PaginatedMetadata[Commenter]],
    response_model_exclude_none=True,
)
async def view(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.view(db=db, payload=payload, page=page, limit=limit)


@router.get(
    "/retrieve_specific_comments/{comment_id}",
    response_model=StandardResponse[Commenter],
    response_model_exclude_none=True,
)
async def view_one(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.fetch_some(
        comment_id=comment_id, db=db, payload=payload
    )


@router.get(
    "/discover",
    response_model=StandardResponse[PaginatedMetadata[Commenter]],
    response_model_exclude_none=True,
)
async def trends(
    sorting=Query("recent", enum=["popular", "recent"]),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.trending(
        sorting=sorting, page=page, limit=limit, db=db, payload=payload
    )


@router.put("/edit", response_model=StandardResponse)
async def edit_comment(
    comment_id: int,
    content: str | None = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.change(
        comment_id=comment_id, content=content, db=db, payload=payload
    )


@router.delete("/delete/{comment_id}", response_model=StandardResponse)
async def delete_one(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await comment_service.delete_one(
        comment_id=comment_id, db=db, payload=payload
    )
