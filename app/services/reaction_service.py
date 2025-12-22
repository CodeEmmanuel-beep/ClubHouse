from app.models_sql import React, Blog, Comment, ReactionType
from app.log.logger import get_loggers
from fastapi import HTTPException, status
from datetime import timezone, datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = get_loggers("react")


async def react_type(
    reaction_type,
    comment_id,
    blog_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Unauthorized reaction attempt")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    try:
        reaction_enum = ReactionType(reaction_type)
    except ValueError:
        logger.warning(f"Invalid reaction type '{reaction_type}' by user {user_id}")
        raise HTTPException(status_code=400, detail="invalid reaction type")
    if (comment_id is None and blog_id is None) or (
        comment_id is not None and blog_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="must input one reaction"
        )
    if blog_id:
        target = await db.get(Blog, blog_id)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="must react on an existing blog",
            )
    if comment_id:
        target = await db.get(Comment, comment_id)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="must react on an existing comment",
            )
    stmt = select(React).where(React.user_id == user_id)
    if blog_id:
        stmt = stmt.where(React.blog_id == blog_id)
    if comment_id:
        stmt = stmt.where(React.comment_id == comment_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        if existing.type == reaction_enum:
            await db.delete(existing)
            if blog_id:
                target.reacts_count = max((target.reacts_count or 1) - 1, 0)
            if comment_id:
                target.reacts_count = max((target.reacts_count or 1) - 1, 0)
            db.add(target)
            await db.commit()
            logger.info(f"User {user_id} removed reaction {existing.id}")
            return {"message": "Reaction removed", "reaction": None}
        existing.type = reaction_enum
        existing.time_of_reaction = datetime.now(timezone.utc)
        try:
            await db.commit()
            await db.refresh(existing)
        except IntegrityError:
            await db.rollback()
            logger.error(f"User {user_id} failed to update reaction {existing.id}")
            raise HTTPException(status_code=500, detail="internal server error")
        logger.info(f"User {user_id} updated reaction {existing.id}")
        return {"message": "Reaction updated", "reaction": existing.type}
    else:
        new_react = React(
            user_id=user_id,
            type=reaction_enum,
            comment_id=comment_id,
            blog_id=blog_id,
            time_of_reaction=datetime.now(timezone.utc),
        )
        try:
            db.add(new_react)
            if blog_id:
                target.reacts_count = (target.reacts_count or 0) + 1
            if comment_id:
                target.reacts_count = (target.reacts_count or 0) + 1
            db.add(target)
            await db.commit()
            await db.refresh(new_react)
        except IntegrityError:
            await db.rollback()
            logger.error(f"User {user_id} failed to add new reaction")
            raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"User {user_id} added new reaction {new_react.id}")
    return {"message": "Reaction added", "reaction": new_react.type}
