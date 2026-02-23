from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from fastapi import Form, File, UploadFile
from app.api.v1.models import LoginResponse, StandardResponse
from app.services import auth_service
from app.utils.helpers import _supabase

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/registration", response_model=StandardResponse, response_model_exclude_none=True
)
async def register(
    profile_picture: UploadFile | None = File(None),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    name: str = Form(...),
    age: float = Form(...),
    nationality: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    get_supabase=Depends(_supabase),
):
    return await auth_service.register(
        db=db,
        profile_picture=profile_picture,
        email=email,
        username=username,
        password=password,
        confirm_password=confirm_password,
        name=name,
        age=age,
        nationality=nationality,
        get_supabase=get_supabase,
    )


@router.post("/logins")
async def login(
    data: LoginResponse, response: Response, db: AsyncSession = Depends(get_db)
):
    return await auth_service.login(db=db, data=data, response=response)


@router.post("/refresh")
async def refresh_token(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    return await auth_service.refresh_token(request=request, response=response)


@router.post("/logout")
async def sign_out(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    return await auth_service.sign_out(db=db, request=request, response=response)
