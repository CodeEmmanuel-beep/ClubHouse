from app.api.v1.models import (
    Chat,
    StandardResponse,
    PaginatedResponse,
)
from app.models_sql import Messaging, User
from fastapi import HTTPException
from datetime import timezone, datetime
from app.log.logger import get_loggers
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, or_, func, and_
import os, shutil, uuid
from werkzeug.utils import secure_filename

logger = get_loggers("chat")


async def text_him(
    message,
    receiver,
    pics,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    try:
        stmt = select(User).where(User.username == receiver, User.is_active == True)
        receive = (await db.execute(stmt)).scalar_one_or_none()
    except Exception as e:
        logger.error(f"Database error while fetching receiver '{receiver}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    if not receive:
        logger.info(f"Message send failed: receiver '{receiver}' not found.")
        raise HTTPException(status_code=404, detail="user not found")
    if pics is not None:
        filename = f"{uuid.uuid4()}_{secure_filename(pics.filename)}"
        file_path = os.path.join("images", filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(pics.file, buffer)
        file_url = f"/images/{filename}"
        pics = file_url
    else:
        pics = None
    if not message and not pics:
        logger.info(f"Message send failed: empty message from user '{username}'.")
        raise HTTPException(status_code=404, detail="can not send empty messages")
    sender = username
    logger.info(f"User '{username}' is sending a message to '{receiver}'.")
    new_message = Messaging(
        user_id=user_id,
        receiver=receiver,
        pics=pics,
        username=sender,
        message=message,
        time_of_chat=datetime.now(timezone.utc),
    )
    try:
        db.add(new_message)
        await db.commit()
        await db.refresh(new_message)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Message send failed due to database error for user '{username}'."
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Message successfully sent from '{username}' to '{receiver}'.")
    return {"success": f"message successfully sent to {receiver}"}


async def view_messages(
    page,
    limit,
    db,
    payload,
):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    offset = (page - 1) * limit
    conversation_key = func.concat(
        func.least(Messaging.username, Messaging.receiver),
        ":",
        func.greatest(Messaging.username, Messaging.receiver),
    )
    stmt = (
        select(Messaging, conversation_key.label("conversation_id"))
        .where(
            or_(
                and_(Messaging.username == username, Messaging.sender_deleted == False),
                and_(
                    Messaging.receiver == username, Messaging.receiver_deleted == False
                ),
            )
        )
        .distinct(conversation_key)
        .order_by(conversation_key, Messaging.time_of_chat.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"Total conversations found for user '{username}': {total}")
    view = (await db.execute(stmt.offset(offset).limit(limit))).all()
    for msg, _ in view:
        if msg.receiver == username:
            msg.delivered = True
    await db.commit()
    conversations = {}
    for msg, conv_id in view:
        conversations.setdefault(conv_id, []).append(Chat.model_validate(msg))
    data = {
        "conversations": conversations,
        "pagination": PaginatedResponse(page=page, limit=limit, total=total),
    }
    logger.info(f"Fetched conversations for user '{username}' (page={page}).")
    return StandardResponse(status="success", message="your messages", data=data)


async def view_message(
    receiver,
    page,
    limit,
    db,
    payload,
):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    offset = (page - 1) * limit
    conversation_key = func.concat(
        func.least(Messaging.username, Messaging.receiver),
        ":",
        func.greatest(Messaging.username, Messaging.receiver),
    )
    stmt = (
        select(Messaging, conversation_key.label("conversation_id"))
        .where(
            or_(
                and_(
                    Messaging.username == username,
                    Messaging.receiver == receiver,
                    Messaging.sender_deleted == False,
                ),
                and_(
                    Messaging.username == receiver,
                    Messaging.receiver == username,
                    Messaging.receiver_deleted == False,
                ),
            )
        )
        .order_by(Messaging.time_of_chat.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"Total messages found between '{username}' and '{receiver}': {total}")
    view = (await db.execute(stmt.offset(offset).limit(limit))).all()
    for msg, _ in view:
        if msg.receiver == username:
            msg.seen = True
    await db.commit()
    conversations = {}
    for msg, conv_id in view:
        conversations.setdefault(conv_id, []).append(Chat.model_validate(msg))
    data = {
        "conversations": conversations,
        "pagination": PaginatedResponse(page=page, limit=limit, total=total),
    }
    logger.info(
        f"Fetched messages between '{username}' and '{receiver}' (page={page})."
    )
    return StandardResponse(status="success", message="your messages", data=data)


async def delete_message(
    message_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user: {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(Messaging).where(Messaging.id == message_id)
    message = (await db.execute(stmt)).scalar_one_or_none()
    if not message:
        logger.info(f"Delete failed: message ID '{message_id}' not found.")
        raise HTTPException(status_code=404, detail="message not found")
    if message.username != username and message.receiver != username:
        logger.warning(
            f"Unauthorized delete attempt by user '{user_id}' on message ID '{message_id}'."
        )
        raise HTTPException(
            status_code=403, detail="not authorized to delete this message"
        )
    if message.username == username:
        message.sender_deleted = True
    elif message.receiver == username:
        message.receiver_deleted = True
    try:
        await db.commit()
    except IntegrityError:
        logger.error(
            f"Failed to delete message ID '{message_id}' by user '{username}'."
        )
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Message ID '{message_id}' deleted by user '{username}'.")
    return {"success": f"message ID {message_id} successfully deleted"}


async def clear_conversation(
    chat_partner,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user: {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(Messaging).where(
        or_(
            ((Messaging.username == username) & (Messaging.receiver == chat_partner)),
            ((Messaging.username == chat_partner) & (Messaging.receiver == username)),
        )
    )
    messages = (await db.execute(stmt)).scalars().all()
    if not messages:
        logger.info(
            f"No messages found between '{username}' and '{chat_partner}' to delete."
        )
        raise HTTPException(status_code=404, detail="no messages found to delete")
    for message in messages:
        if message.username == username:
            message.sender_deleted = True
        elif message.receiver == username:
            message.receiver_deleted = True
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Failed to clear conversation between '{username}' and '{chat_partner}'."
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"All messages between '{username}' and '{chat_partner}' deleted by user '{username}'."
    )
    return {"success": f"all messages with {chat_partner} successfully deleted"}
