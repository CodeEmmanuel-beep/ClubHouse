from fastapi import APIRouter, Depends, Query, Form, File, UploadFile, Request
from app.api.v1.models import StandardResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.services import profile_service
from app.utils.helpers import _supabase


router = APIRouter(prefix="/info", tags=["Profile"])


@router.get(
    "/profile",
    response_model=StandardResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.view(db=db, payload=payload, request=request)


@router.get(
    "/search/{name}",
    response_model=StandardResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
async def other_users(
    request: Request,
    name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.other_users(
        name=name, db=db, payload=payload, page=page, limit=limit, request=request
    )


@router.put("/edit_profile")
async def edit_profile(
    profile_picture: UploadFile | None = File(None),
    name: str | None = Form(None),
    nationality: str | None = Form(None),
    address: str | None = Form(None),
    age: int | None = Form(None),
    phone_number: float | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
    get_supabase=Depends(_supabase),
):
    return await profile_service.profile(
        profile_picture=profile_picture,
        name=name,
        nationality=nationality,
        address=address,
        age=age,
        phone_number=phone_number,
        db=db,
        payload=payload,
        get_supabase=get_supabase,
    )


@router.delete("/delete_profile")
async def delete_self(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.delete_profile(db=db, payload=payload)
