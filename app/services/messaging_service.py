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
from sqlalchemy import select, or_, func, and_, update
from sqlalchemy.orm import selectinload
import uuid
from werkzeug.utils import secure_filename
from app.utils.helpers import generate_signed_urls

logger = get_loggers("chat")


async def text_him(message, receiver, pics, db, payload, get_supabase):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    try:
        stmt = select(User).where(User.id == receiver, User.is_active == True)
        receive = (await db.execute(stmt)).scalar_one_or_none()
    except Exception as e:
        logger.error(f"Database error while fetching receiver '{receiver}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    if not receive:
        logger.info(f"Message send failed: receiver '{receiver}' not found.")
        raise HTTPException(status_code=404, detail="user not found")
    filename = None
    if pics is not None:
        try:
            filename = f"{uuid.uuid4()}_{secure_filename(pics.filename)}"
            file_bytes = await pics.read()
            res = await get_supabase.storage.from_("codeemmanuel").upload(
                filename, file_bytes, {"content-type": pics.content_type}
            )
            if hasattr(res, "error"):
                logger.error("Error uploading photo %s", res)
                raise HTTPException(status_code=500, detail="error uploading photo")
        except Exception as e:
            logger.exception(f"failed to send photo {e}")
            pics = None
            raise HTTPException(status_code=500, detail="Error sending photo")
    else:
        pics = None
    if not message and not pics:
        logger.info(f"Message send failed: empty message from user '{username}'.")
        raise HTTPException(status_code=404, detail="can not send empty messages")
    logger.info(f"User '{username}' is sending a message to '{receiver}'.")
    new_message = Messaging(
        user_id=user_id,
        receiver=receive.id,
        pics=filename,
        message=message,
        time_of_chat=datetime.now(timezone.utc),
    )
    try:
        db.add(new_message)
        await db.commit()
        await db.refresh(new_message)
    except IntegrityError:
        await db.rollback()
        if filename:
            cleanup = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleanup, "error"):
                logger.error("unable to remove orphaned file %s", cleanup)
            logger.warning("removed orphaned file after rollback:%s", filename)
        logger.error(
            f"Message send failed due to database error for user '{username}'."
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        if filename:
            cleanup = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleanup, "error"):
                logger.error("unable to remove orphaned file %s", cleanup)
            logger.warning("removed orphaned file after rollback:%s", filename)
        logger.exception(
            f"Message send failed due to internal server error for user '{username}'."
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Message successfully sent from '{username}' to '{receiver}'.")
    return {"success": f"message successfully sent to {receive.name}"}


async def view_messages(page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    conversation_key = func.concat(
        func.least(Messaging.user_id, Messaging.receiver),
        ":",
        func.greatest(Messaging.user_id, Messaging.receiver),
    )
    stmt = (
        select(Messaging, conversation_key.label("conversation_id"))
        .options(selectinload(Messaging.user))
        .where(
            or_(
                and_(Messaging.user_id == user_id, Messaging.sender_deleted == False),
                and_(
                    Messaging.receiver == user_id, Messaging.receiver_deleted == False
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
    await db.execute(
        update(Messaging)
        .where(Messaging.receiver == user_id, Messaging.delivered == False)
        .values(delivered=True)
    )
    await db.commit()
    filenames = [v.pics for v, _ in view if v.pics]
    files = await generate_signed_urls(request, filenames, context="picture message")
    logger.info(f"message value updated for username, {username}")
    conversations = {}
    for msg, conv_id in view:
        chatter = Chat.model_validate(msg)
        chatter.name = msg.user.name
        pic = msg.pics if msg.pics else None
        chatter.pics = files.get(pic) if pic else None
        conversations.setdefault(conv_id, []).append(chatter)
    data = {
        "conversations": conversations,
        "pagination": PaginatedResponse(page=page, limit=limit, total=total),
    }
    logger.info(f"Fetched conversations for user '{username}' (page={page}).")
    return StandardResponse(status="success", message="your messages", data=data)


async def view_message(receiver, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt by user: {username}")
        raise HTTPException(status_code=403, detail="not a valid user")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    conversation_key = func.concat(
        func.least(Messaging.user_id, Messaging.receiver),
        ":",
        func.greatest(Messaging.user_id, Messaging.receiver),
    )
    stmt = (
        select(Messaging, conversation_key.label("conversation_id"))
        .options(selectinload(Messaging.user))
        .where(
            or_(
                and_(
                    Messaging.user_id == user_id,
                    Messaging.receiver == receiver,
                    Messaging.sender_deleted == False,
                ),
                and_(
                    Messaging.user_id == receiver,
                    Messaging.receiver == user_id,
                    Messaging.receiver_deleted == False,
                ),
            )
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"Total messages found between '{username}' and '{receiver}': {total}")
    view = (await db.execute(stmt.offset(offset).limit(limit))).all()
    filenames = [v.pics for v, _ in view if v.pics]
    files = await generate_signed_urls(request, filenames, context="message photo")
    for msg, _ in view:
        if msg.receiver == user_id:
            msg.seen = True
    await db.commit()
    conversations = {}
    for msg, conv_id in view:
        chatter = Chat.model_validate(msg)
        chatter.name = msg.user.name
        filename = msg.pics if msg.pics else None
        chatter.pics = files.get(filename) if filename else None
        conversations.setdefault(conv_id, []).append(chatter)
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
    if message.user_id != user_id and message.receiver != user_id:
        logger.warning(
            f"Unauthorized delete attempt by user '{user_id}' on message ID '{message_id}'."
        )
        raise HTTPException(status_code=403, detail="message not found ")
    if message.user_id == user_id:
        message.sender_deleted = True
    elif message.receiver == user_id:
        message.receiver_deleted = True
    try:
        await db.commit()
    except IntegrityError:
        logger.error(f"Failed to delete message ID '{message_id}' by user '{user_id}'.")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        logger.exception(
            f"Failed to delete message ID '{message_id}' by user '{user_id}'."
        )
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Message ID '{message_id}' deleted by user '{user_id}'.")
    return {"success": f"message ID {message_id} successfully deleted"}


async def clear_conversation(
    chat_id,
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
            ((Messaging.user_id == user_id) & (Messaging.receiver == chat_id)),
            ((Messaging.user_id == chat_id) & (Messaging.receiver == user_id)),
        )
    )
    messages = (await db.execute(stmt)).scalars().all()
    if not messages:
        logger.info(
            f"No messages found between '{username}' and '{chat_id}' to delete."
        )
        raise HTTPException(status_code=404, detail="no messages found to delete")
    for message in messages:
        if message.user_id != user_id and message.receiver != user_id:
            logger.warning(
                f"Unauthorized clear attempt by user '{user_id}' on conversation with '{chat_id}'."
            )
            raise HTTPException(status_code=403, detail="no messages found to delete")
        if message.user_id == user_id:
            message.sender_deleted = True
        elif message.receiver == user_id:
            message.receiver_deleted = True
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Failed to clear conversation between '{username}' and '{chat_id}'."
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"Failed to clear conversation between '{username}' and '{chat_id}'."
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"All messages between '{username}' and '{chat_id}' deleted by user '{username}'."
    )
    return {"success": f"all messages with {chat_id} successfully deleted"}
