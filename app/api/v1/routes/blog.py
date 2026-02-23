from fastapi import APIRouter, Depends, Query, File, Form, UploadFile, Request
from app.api.v1.models import (
    Blogger,
    PaginatedMetadata,
    StandardResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from typing import List
from app.services import blog_service
from app.utils.helpers import _supabase

router = APIRouter(prefix="/blogs", tags=["Blog"])


@router.post("/expressions")
async def express(
    image: List[UploadFile] | None = File(None),
    target: str | None = Form(None),
    details: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
    get_supabase=Depends(_supabase),
):
    return await blog_service.create_blog(
        db=db,
        payload=payload,
        image=image,
        target=target,
        details=details,
        get_supabase=get_supabase,
    )


@router.get(
    "/view",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def view(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.retrieve_all(
        db=db, payload=payload, page=page, limit=limit, request=request
    )


@router.get(
    "/search",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def sift(
    request: Request,
    author: str | None = None,
    target: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.filter(
        db=db,
        payload=payload,
        author=author,
        target=target,
        page=page,
        limit=limit,
        request=request,
    )


@router.get(
    "/discover",
    response_model=StandardResponse[PaginatedMetadata[Blogger]],
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def trends(
    request: Request,
    sorting: str = Query("recent", enum=["popular", "recent"]),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.view_trending(
        db=db, payload=payload, sorting=sorting, page=page, limit=limit, request=request
    )


@router.get(
    "/retrieve_specific_blogs/{blog_id}",
    response_model=StandardResponse[Blogger],
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def view_one(
    request: Request,
    blog_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await blog_service.fetch_some(
        db=db, payload=payload, blog_id=blog_id, request=request
    )


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
    get_supabase=Depends(_supabase),
):
    return await blog_service.delete_one(
        db=db, payload=payload, blog_id=blog_id, get_supabase=get_supabase
    )


@router.delete("/clear_all")
async def delete_all(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
    get_supabase=Depends(_supabase),
):
    return await blog_service.clear(db=db, payload=payload, get_supabase=get_supabase)
