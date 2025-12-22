from fastapi import (
    APIRouter,
    Depends,
    Query,
    Form,
    File,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.services import profile_service


router = APIRouter(prefix="/info", tags=["Profile"])


@router.get(
    "/profile",
)
async def view(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.view(db=db, payload=payload, page=page, limit=limit)


@router.get(
    "/search",
)
async def other_users(
    name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.other_users(
        name=name, db=db, payload=payload, page=page, limit=limit
    )


@router.put("/edit_p")
async def edit_profile(
    profile_picture: UploadFile | None = File(None),
    name: str | None = Form(None),
    nationality: str | None = Form(None),
    address: str | None = Form(None),
    age: int | None = Form(None),
    phone_number: float | None = Form(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
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
    )


@router.delete("/delete_profile")
async def delete_self(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await profile_service.delete_profile(db=db, payload=payload)
