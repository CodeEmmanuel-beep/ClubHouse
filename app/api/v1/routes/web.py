from fastapi import (
    WebSocket,
    WebSocketDisconnect,
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from app.core.db_session import get_db
from sqlalchemy import select, or_
from typing import Dict
from app.models_sql import Messaging, User
from app.log.logger import get_loggers
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.core.scheduler import send_email_name
from jose import jwt, JWTError
from app.core.config import settings


router = APIRouter(prefix="/Chatbox", tags=["instantmessaging"])
logger = get_loggers("ichat")

active_connections: Dict[int, WebSocket] = {}


async def connect(user_id: int, web: WebSocket, db: AsyncSession):
    await web.accept()
    active_connections[user_id] = web
    stmt = select(Messaging).where(
        Messaging.receiver_id == user_id, Messaging.delivered.is_(False)
    )
    pending = (await db.execute(stmt)).scalars().all()
    for msg in pending:
        if msg.message:
            await web.send_text(f"{msg.user_id}: {msg.message}")
        if msg.pics:
            await web.send_bytes(msg.pics)
        msg.delivered = True
        db.add(msg)
        await db.commit()


async def disconnect(user_id: int):
    if user_id in active_connections:
        del active_connections[user_id]


@router.websocket("/chat/{username}")
async def chatterbox(
    web: WebSocket,
    username: str,
    talk_id: int = Query(...),
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("user_id")
        username_from_token = payload.get("sub")
    except JWTError as e:
        print(f"error: {e}")
        await web.close(code=4002)
        return
    if not username_from_token:
        await web.close(code=4003)
        return
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="forbidden access")
    stmt = select(User).where(User.id == talk_id)
    tap = (await db.execute(stmt)).scalar_one_or_none()
    if not tap:
        raise HTTPException(status_code=404, detail="user not found")
    await connect(user_id, web, db)
    logger.info(f"{username} ({user_id}) connected to chat with {talk_id}")
    try:
        while True:
            message = await web.receive()
            if "text" in message:
                data = message["text"]
                delivered = False
                logger.info(f"Processing text message from {username} to {talk_id}")
                if talk_id in active_connections:
                    try:
                        await active_connections[talk_id].send_text(
                            f"{username}:{data}"
                        )
                        delivered = True
                        logger.info(
                            f"Delivered message from {username} -> {talk_id}: {data}"
                        )
                    except Exception:
                        pass
                messages = Messaging(
                    user_id=user_id,
                    receiver_id=talk_id,
                    username=username_from_token,
                    message=data,
                    time_of_chat=datetime.now(timezone.utc),
                    delivered=delivered,
                )
                db.add(messages)
                await db.commit()
                await db.refresh(messages)
                logger.debug(
                    f"Stored message in DB (ID: {messages.id}) from {username} -> {talk_id}"
                )

            if "bytes" in message:
                mata = message["bytes"]
                delivered = False
                logger.debug(f"Processing binary data from {username} to {talk_id}")
                if talk_id in active_connections:
                    try:
                        await active_connections[talk_id].send_bytes(mata)
                        delivered = True
                        logger.info(f"Delivered image from {username} -> {talk_id}")
                    except Exception:
                        pass
                pictures = Messaging(
                    user_id=user_id,
                    receiver_id=talk_id,
                    username=username_from_token,
                    pics=mata,
                    time_of_chat=datetime.now(timezone.utc),
                    delivered=delivered,
                )
                db.add(pictures)
                await db.commit()
                await db.refresh(pictures)
                logger.debug(
                    f"Stored image in DB (ID: {pictures.id}) from {username} -> {talk_id}"
                )
    except WebSocketDisconnect:
        await disconnect(user_id)
        logger.info(f"{username} disconnected")
        send_email_name.apply_async(
            kwargs={
                "subject": "missed chat",
                "body": f"you have unread chat from {username}",
                "to_email": tap.email,
            },
            countdown=600,
        )
    finally:
        await web.close()
        await db.close()
        logger.info(f"WebSocket and DB closed for {username} ({user_id})")
