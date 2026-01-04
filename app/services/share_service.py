from app.models_sql import Blog, Share, ShareType, User, Comment
from app.log.logger import get_loggers
from fastapi import HTTPException, status
from datetime import timezone, datetime
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.api.v1.models import (
    PaginatedResponse,
    Sharer,
    StandardResponse,
    PaginatedMetadata,
    Blogger,
    CommentResponse,
)
from app.services.blog_service import blog_react_summary
from app.services.comment_service import react_summary

logger = get_loggers("share")


async def sharing(
    blog_id,
    content,
    react_type,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Forbidden: user_id missing in payload")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    share_emu = None
    if react_type:
        try:
            share_emu = ShareType(react_type)
            logger.info("Share type parsed: %s", share_emu)
        except ValueError:
            logger.error("Invalid share type: %s", react_type)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="input a valid reaction"
            )
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .where(Blog.id == blog_id, User.is_active == True)
    )
    blog = (await db.execute(stmt)).scalar_one_or_none()
    if not blog:
        logger.error("Blog not found. blog_id: %s", blog_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    new_share = Share(
        user_id=user_id,
        type=share_emu,
        content=content,
        blog_id=blog_id,
        time_of_share=datetime.now(timezone.utc),
    )
    try:
        db.add(new_share)
        blog.share_count = (blog.share_count or 0) + 1
        db.add(blog)
        await db.commit()
        await db.refresh(new_share)
        logger.info(
            "New share created. share_id: %s, user_id: %s", new_share.id, user_id
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return "blog shared"


async def views(
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Forbidden access: user_id missing in payload")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    offset = (page - 1) * limit
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(User.is_active == True)
        .order_by(
            Blog.time_of_post.desc(),
            (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
        )
    )
    result = await db.execute(stmt)
    logger.info(f"Fetching blogs for active users for user: {user_id}")
    blogs = result.scalars().all()
    comment = (
        (
            await db.execute(
                select(Comment)
                .join(User, User.id == Comment.user_id)
                .options(selectinload(Comment.user))
                .where(User.is_active == True)
                .order_by(
                    Comment.time_of_post.desc(),
                    Comment.reacts_count.desc(),
                )
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    logger.info("Fetching recent comments")
    comment_ids = [c.id for c in comment]
    maps = await react_summary(db, comment_ids)
    comment_response = []
    for com in comment:
        comment_data = CommentResponse.model_validate(com)
        comment_data.profile_picture = com.user.profile_picture
        comment_data.name = com.user.name
        comment_data.reactions = (
            maps.get(com.id) if comment_data.reacts_count > 0 else None
        )
        logger.info(comment_data.reactions)
        comment_response.append(comment_data)
    blog_ids = [b.id for b in blogs]
    blog_reaction_map = await blog_react_summary(db, blog_ids)
    blog_response = []
    for blog in blogs:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = (
            blog_reaction_map.get(blog.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = [c for c in comment_response if c.blog_id == blog.id]
        blog_response.append(blog_data)
    stmt = (
        (
            select(Share)
            .join(User, User.id == Share.user_id)
            .options(
                selectinload(Share.user),
                selectinload(Share.blog).selectinload(Blog.comments),
            )
        )
        .where(User.is_active == True)
        .order_by(Share.time_of_share.desc())
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        logger.warning("No shares found for given pagination")
        raise HTTPException(status_code=404, detail="No shares found")
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    items = []
    for share in result:
        share_data = Sharer.model_validate(share)
        share_data.profile_picture = share.user.profile_picture
        share_data.name = share.user.name
        share_data.blog = [b for b in blog_response if b.id == share.blog_id]
        items.append(share_data)
    data = PaginatedMetadata[Sharer](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"Returning {len(items)} shares out of total {total}")
    return StandardResponse(status="success", message="shares", data=data)


async def view(
    share_id,
    session,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Forbidden access: user_id missing in payload")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(User.is_active == True)
        .order_by(
            Blog.time_of_post.desc(),
            (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
        )
    )
    result = await session.execute(stmt)
    blogs = result.scalars().all()
    logger.info(f"Fetching blogs for active users")
    comment = (
        (
            await session.execute(
                select(Comment)
                .join(User, User.id == Comment.user_id)
                .options(selectinload(Comment.user))
                .where(User.is_active == True)
                .order_by(
                    Comment.time_of_post.desc(),
                    Comment.reacts_count.desc(),
                )
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    logger.info("Fetching recent comments")
    comment_ids = [c.id for c in comment]
    maps = await react_summary(session, comment_ids)
    comment_response = []
    for com in comment:
        comment_data = CommentResponse.model_validate(com)
        comment_data.profile_picture = com.user.profile_picture
        comment_data.name = com.user.name
        comment_data.reactions = (
            maps.get(com.id) if comment_data.reacts_count > 0 else None
        )
        logger.info(comment_data.reactions)
        comment_response.append(comment_data)
    blog_ids = [b.id for b in blogs]
    blog_reaction_map = await blog_react_summary(session, blog_ids)
    blog_response = []
    for blog in blogs:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = (
            blog_reaction_map.get(blog.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = [c for c in comment_response if c.blog_id == blog.id]
        blog_response.append(blog_data)
    stmt = (
        (
            select(Share)
            .join(User, User.id == Share.user_id)
            .options(
                selectinload(Share.user),
                selectinload(Share.blog).selectinload(Blog.comments),
            )
        )
        .where(User.is_active == True, Share.id == share_id)
        .order_by(Share.time_of_share.desc())
    )
    result = (await session.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning("No shares found for given pagination")
        return StandardResponse(status="error", message="invalid share_id")
    data = Sharer.model_validate(result)
    data.profile_picture = result.user.profile_picture
    data.name = result.user.name
    data.blog = [b for b in blog_response if b.id == result.blog_id]
    logger.info(f"Returning share data for user: {user_id}")
    return StandardResponse(status="success", message="your shared blogs", data=data)


async def delete_one(
    share_id: int,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning("Unauthorized delete attempt detected (no user_id in payload)")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Share).where(Share.user_id == user_id, Share.id == share_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning("User not found: user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="invalid field")
    sharer = await db.get(Blog, data.blog_id)
    try:
        await db.delete(data)
        sharer.share_count = max((sharer.share_count or 1) - 1, 0)
        await db.commit()
        logger.info("delete_one endpoint completed successfully")
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            "IntegrityError while updating profile for user_id=%s: %s", user_id, str(e)
        )
        raise HTTPException(status_code=500, detail="internal server error")
    return {
        "status": "success",
        "message": "share successfully deleted",
        "data": {
            "id": data.id,
            "user": username,
        },
    }
