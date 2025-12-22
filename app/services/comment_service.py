from fastapi import HTTPException
from app.api.v1.models import (
    StandardResponse,
    PaginatedResponse,
    PaginatedMetadata,
    Commenter,
    ReactionsSummary,
)
from app.models_sql import Comment, Blog, User, React
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.log.logger import get_loggers
import tracemalloc

tracemalloc.start()

logger = get_loggers("comments")


async def react_summary(db: AsyncSession, comment_id) -> ReactionsSummary:
    counts = (
        await db.execute(
            select(React.type, func.count(React.id))
            .where(React.comment_id == comment_id)
            .group_by(React.type)
            .order_by(React.type)
        )
    ).all()
    summary = {
        rtype.name if hasattr(rtype, "name") else rtype: count
        for rtype, count in counts
    }
    return ReactionsSummary(
        like=summary.get("like", 0),
        love=summary.get("love", 0),
        laugh=summary.get("laugh", 0),
        angry=summary.get("angry", 0),
        wow=summary.get("wow", 0),
        sad=summary.get("sad", 0),
    )


async def c_express(comment, db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    target = await db.get(Blog, comment.blog_id)
    if not target:
        logger.warning(f"No blog found with ID: {comment.blog_id}")
        return StandardResponse(status="failure", message="no such blog exists")
    comments = Comment(
        user_id=user_id,
        content=comment.content,
        blog_id=comment.blog_id,
        time_of_post=datetime.now(timezone.utc),
    )
    try:
        db.add(comments)
        target.comments_count = (target.comments_count or 0) + 1
        await db.commit()
        await db.refresh(comments)
    except IntegrityError:
        logger.info(f"comment creation failed by:{user_id}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"Comment successfully committed to database by {username} with ID: {comments.id if hasattr(comments, 'id') else 'unknown'}"
    )
    data = Commenter.model_validate(comments)
    return StandardResponse(status="success", message="post successful", data=[data])


async def view(page, limit, db, payload):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    stmt = select(Comment).options(selectinload(Comment.user))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    items = []
    for comment in result:
        comment_data = Commenter.model_validate(comment)
        comment_data.profile_picture = comment.user.profile_picture
        comment_data.name = comment.user.name
        comment_data.reactions = await react_summary(db, comment.id)
        items.append(comment_data)
    data = PaginatedMetadata[Commenter](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"Fetched {len(result)} comments for user={user_id} (page={page}).")
    return StandardResponse(status="success", message="comments", data=data)


async def fetch_some(comment_id, db, payload):
    user_id = payload.get("user_id")
    logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = (
        select(Comment)
        .options(selectinload(Comment.user))
        .where(Comment.id == comment_id)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.info(f"No comment found for com_id={comment_id}")
        return StandardResponse(status="failure", message="invalid id")
    data = Commenter.model_validate(result)
    data.profile_picture = result.user.profile_picture
    data.name = result.user.name
    data.reactions = await react_summary(db, result.id)
    logger.info(f"Successfully fetched comment com_id={comment_id} for user={user_id}")
    return StandardResponse(status="success", message="requested data", data=data)


async def trending(sorting, page, limit, db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    stmt = select(Comment).options(selectinload(Comment.user))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    if sorting == "recent":
        stmt = stmt.order_by(Comment.time_of_post.desc())
    if sorting == "popular":
        stmt = stmt.order_by(Comment.reacts_count.desc())
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    items = []
    for comment in result:
        comment_data = Commenter.model_validate(comment)
        comment_data.profile_picture = comment.user.profile_picture
        comment_data.name = comment.user.name
        comment_data.reactions = await react_summary(db, comment.id)
        items.append(comment_data)
    data = PaginatedMetadata[Commenter](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"Fetched {len(result)} comments for user={username} (page={page})")
    return StandardResponse(status="success", message="comments", data=data)


async def change(comment_id, content, db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(
            "Unauthorized access attempt — missing user_id in token payload."
        )
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Comment).where(Comment.user_id == user_id, Comment.id == comment_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.debug(f"Updating content for blog_id={comment_id}")
        logger.info(
            f"Invalid edit attempt: blog_id={comment_id} not found for user_id={user_id}."
        )
        raise HTTPException(status_code=400, detail="invalid section")
    if content:
        data.content = content
    data.time_of_post = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(data)
    except IntegrityError:
        await db.rollback()
        logger.info(f"failed to edit comment for user_id:{user_id}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"Successfully edited blog_id={data.id} by user={username} (ID={user_id})"
    )
    return {
        "status": "success",
        "message": "edited counter",
        "data": {
            "id": data.id,
            "content": data.content,
            "commencement": data.time_of_post,
        },
    }


async def delete_one(comment_id, db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(
            "Unauthorized access attempt — missing user_id in token payload."
        )
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Comment).where(Comment.user_id == user_id, Comment.id == comment_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.info(
            f"No comment found for comment_id={comment_id} and user_id={user_id}."
        )
        return {"status": "no data", "message": "invalid field"}
    target = await db.get(Blog, data.blog_id)
    try:
        await db.delete(data)
        target.comments_count = max((target.comments_count or 1) - 1, 0)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info(
            f"failed to delete comment, with comment id:{comment_id}, for user:{user_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")

    logger.info(
        f"Comment deleted successfully — blog_id={data.id}, user={username} (ID={user_id})"
    )
    return {
        "status": "success",
        "message": "comment successfully deleted",
        "data": {
            "id": data.id,
            "username": username,
        },
    }
