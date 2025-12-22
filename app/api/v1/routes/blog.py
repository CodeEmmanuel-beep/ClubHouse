from fastapi import APIRouter, Depends, Query, File, Form, UploadFile
from app.api.v1.models import (
    Blogger,
    PaginatedMetadata,
    StandardResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.log.logger import get_loggers
from typing import List
from app.services import blog_service

router = APIRouter(prefix="/blogs", tags=["Blog"])
logger = get_loggers("blogs")


@router.post("/expressionns")
async def express(
    image: List[UploadFile] | None = File(None),
    target: str | None = Form(None),
    details: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.create_blog(
        db=db, payload=payload, image=image, target=target, details=details
    )


@router.get(
    "/view",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
)
async def view(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.retrieve_all(
        db=db, payload=payload, page=page, limit=limit
    )


@router.get(
    "/search",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
)
async def sift(
    author: str | None = None,
    target: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.filter(
        db=db, payload=payload, author=author, target=target, page=page, limit=limit
    )


@router.get(
    "/discover",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
)
async def trends(
    sorting: str = Query("recent", enum=["popular", "recent"]),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.view_trending(
        db=db, payload=payload, sorting=sorting, page=page, limit=limit
    )


@router.get(
    "/retrieve_specific_blogs/{blog_id}",
    response_model=StandardResponse[Blogger],
    response_model_exclude_none=True,
)
async def view_one(
    blog_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.fetch_some(db=db, payload=payload, blog_id=blog_id)


@router.put("/edit", response_model=StandardResponse)
async def edit_blog(
    blog_id: int,
    target: str | None = None,
    details: str | None = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.change(
        db=db, payload=payload, blog_id=blog_id, target=target, details=details
    )


@router.delete("/erase/{blog_id}", response_model=StandardResponse)
async def delete_one(
    blog_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.delete_one(db=db, payload=payload, blog_id=blog_id)


@router.delete("/clear_all")
async def delete_all(
    db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_token)
):
    return await blog_service.clear(db=db, payload=payload)
