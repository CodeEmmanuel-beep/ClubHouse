from app.api.v1.models import (
    StandardResponse,
)
from fastapi import APIRouter, Depends, Query, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.services import messaging_service

router = APIRouter(prefix="/message", tags=["Chat_up"])


@router.post("/send")
async def send(
    message: str | None = None,
    receiver: str | None = None,
    pics: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await messaging_service.text_him(
        message=message,
        receiver=receiver,
        pics=pics,
        db=db,
        payload=payload,
    )


@router.get(
    "/view",
    response_model=StandardResponse,
    response_model_exclude_none=True,
)
async def view_messages(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await messaging_service.view_messages(
        page=page, limit=limit, db=db, payload=payload
    )


@router.get(
    "/view_one",
    response_model=StandardResponse,
    response_model_exclude_none=True,
)
async def view_message(
    receiver: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await messaging_service.view_message(
        receiver=receiver, page=page, limit=limit, db=db, payload=payload
    )


@router.delete("/delete_message/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await messaging_service.delete_message(
        message_id=message_id, db=db, payload=payload
    )


@router.delete("/clear_conversation")
async def clear_conversation(
    chat_partner: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await messaging_service.clear_conversation(
        chat_partner=chat_partner, db=db, payload=payload
    )
