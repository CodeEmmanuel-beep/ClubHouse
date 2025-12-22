from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from fastapi import Form, File, UploadFile
from app.api.v1.models import LoginResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/registration")
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
    return await auth_service.refresh_token(db=db, request=request, response=response)


@router.post("/logout")
async def sign_out(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    return await auth_service.sign_out(db=db, request=request, response=response)
