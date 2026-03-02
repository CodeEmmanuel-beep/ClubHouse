from fastapi import HTTPException
from app.api.v1.models import (
    StandardResponse,
    PaginatedResponse,
    PaginatedMetadata,
    CommentResponse,
)
from app.models_sql import Comment, Blog, User
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.log.logger import get_loggers
from app.utils.redis import cache_invalidation
import tracemalloc
import asyncio
from app.utils.helpers import (
    generate_signed_urls,
    generate_signed_url,
    build_comment_response,
)
from app.utils.redis import caching, cached
from app.utils.reactions_count import react_summary

tracemalloc.start()

logger = get_loggers("comments")


async def c_express(comment, db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    target = await db.get(Blog, comment.blog_id)
    if not target:
        logger.warning(f"No blog found with ID: {comment.blog_id}")
        raise HTTPException(status_code=404, detail="blog not found")
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
        await cache_invalidation(user_id)
    except IntegrityError:
        logger.error(f"comment creation failed by:{user_id}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        logger.exception("comment creation failed by%s: %s", user_id, e)
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"Comment successfully committed to database by {username} with ID: {comments.id if hasattr(comments, 'id') else 'unknown'}"
    )
    return {"status": "success", "message": "post successful"}


async def view(page, limit, db, payload, request):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_url = f"comment_url:{page}:{limit}"
    cached_data = await caching(cache_url)
    if cached_data:
        logger.info(f"Cache hit for user_id: {user_id}, page: {page}, limit: {limit}")
        profile_pics = cached_data.get("profile_picture", {})
    stmt = (
        select(Comment)
        .join(Comment.user)
        .options(selectinload(Comment.user))
        .where(User.is_active == True)
    ).order_by(Comment.time_of_post.desc(), Comment.reacts_count.desc())
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        logger.info(f"No comments found for user_id={user_id} (page={page}).")
        raise HTTPException(status_code=404, detail="no comments")
    logger.info("Number of comments retrieved on this page: %d", len(result))
    filenames = [c.user.profile_picture for c in result if c.user.profile_picture]
    comment_id = [c.id for c in result]
    sub_total, reaction_map = await asyncio.gather(
        db.execute(
            select(func.count(Comment.id))
            .join(Comment.user)
            .where(User.is_active == True)
        ),
        react_summary(db, comment_id),
    )
    total = sub_total.scalar() or 0
    logger.info(f"Total comments count: {total}")
    if not cached_data:
        profile_pics = await generate_signed_urls(
            request, filenames, context="commenter profile picture"
        )
        url = {"profile_picture": profile_pics}
        await cached(cache_url, url, ttl=2000)
        logger.info(
            f"Cached profile pictures for user_id: {user_id}, page: {page}, limit: {limit}"
        )
    items = []
    for r in result:
        comment_data = build_comment_response(r, profile_pics, reaction_map)
        items.append(comment_data)
    data = PaginatedMetadata[CommentResponse](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"Fetched {len(result)} comments for user={user_id} (page={page}).")
    return StandardResponse(status="success", message="comments", data=data)


async def view_blog_comments(blog_id, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_url = f"blog_comments:{blog_id}:{page}:{limit}"
    cached_data = await caching(cache_url)
    if cached_data:
        logger.info(f"Cache hit for blog_id: {blog_id}, page: {page}, limit: {limit}")
        profile_pics = cached_data.get("profile_picture", {})
    stmt = (
        select(Comment)
        .join(User, User.id == Comment.user_id)
        .options(selectinload(Comment.user))
        .where(User.is_active == True, Comment.blog_id == blog_id)
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        logger.info(f"No comments found for blog_id={blog_id} (page={page}).")
        raise HTTPException(status_code=404, detail="no comments")
    logger.info("Number of comments retrieved on this page: %d", len(result))
    comments_id = [c.id for c in result]
    sub_total, react_map = await asyncio.gather(
        db.execute(
            select(func.count(Comment.id)).join(User).where(User.is_active == True)
        ),
        react_summary(db, comments_id),
    )
    total = sub_total.scalar() or 0
    logger.info(f"Total comments count for blog_id={blog_id}: {total}")
    if not cached_data:
        filenames = [c.user.profile_picture for c in result if c.user.profile_picture]
        profile_pics = await generate_signed_urls(
            request, filenames, context="commenter profile picture"
        )
        url = {"profile_picture": profile_pics}
        await cached(cache_url, url, ttl=2000)
    items = []
    for r in result:
        comment_data = build_comment_response(r, profile_pics, react_map)
        items.append(comment_data)
    data = PaginatedMetadata[CommentResponse](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"Fetched {len(result)} comments for user={user_id} (page={page}).")
    return StandardResponse(status="success", message="comments", data=data)


async def fetch_some(comment_id, db, payload, request):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = (
        select(Comment)
        .join(User, User.id == Comment.user_id)
        .options(selectinload(Comment.user))
        .where(Comment.id == comment_id, User.is_active == True)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.info(f"No comment found for com_id={comment_id}")
        return StandardResponse(status="failure", message="invalid id")
    logger.info(f"fetching comment comment_id={comment_id}")
    summary = await react_summary(db, result.id)
    data = CommentResponse.model_validate(result)
    if result.user.profile_picture:
        data.profile_picture = await generate_signed_url(
            request, result.user.profile_picture, context="commenter profile picture"
        )
    else:
        data.profile_picture = None
    data.name = result.user.name
    data.reactions = summary.get(result.id) if data.reacts_count > 0 else None
    logger.info(
        f"Successfully fetched comment comment_id={comment_id} for user={user_id}"
    )
    return StandardResponse(status="success", message="requested data", data=data)


async def trending(sorting, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning("Unauthorized access attempt — missing 'sub' in token payload.")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_url = f"trending_comments:{sorting}:{page}:{limit}"
    cached_data = await caching(cache_url)
    if cached_data:
        logger.info(
            f"Cache hit for trending comments with sorting: {sorting}, page: {page}, limit: {limit}"
        )
        profile_pics = cached_data.get("profile_picture", {})
    stmt = stmt = (
        select(Comment)
        .join(User, User.id == Comment.user_id)
        .options(selectinload(Comment.user))
        .where(User.is_active == True)
    )
    if sorting == "recent":
        stmt = stmt.order_by(Comment.time_of_post.desc())
    if sorting == "popular":
        stmt = stmt.order_by(Comment.reacts_count.desc())
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    logger.info("Number of comments retrieved on this page: %d", len(result))
    comment_id = [c.id for c in result]
    sub_total, reaction_map = await asyncio.gather(
        db.execute(
            select(func.count(Comment.id)).join(User).where(User.is_active == True)
        ),
        react_summary(db, comment_id),
    )
    total = sub_total.scalar() or 0
    logger.info(f"Total comments count: {total}")
    if not cached_data:
        filenames = [c.user.profile_picture for c in result if c.user.profile_picture]
        profile_pics = await generate_signed_urls(
            request, filenames, context="commenter profile picture"
        )
        url = {"profile_picture": profile_pics}
        await cached(cache_url, url, ttl=2000)
    items = []
    for r in result:
        comment_data = build_comment_response(r, profile_pics, reaction_map)
        items.append(comment_data)
    data = PaginatedMetadata[CommentResponse](
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
        logger.info(
            f"Invalid edit attempt: blog_id={comment_id} not found for user_id={user_id}."
        )
        raise HTTPException(status_code=400, detail="invalid section")
    if content:
        data.content = content
    data.time_of_post = datetime.now(timezone.utc)
    logger.info(f"edit attempt by {user_id} on comment with id:{data.id}")
    try:
        await db.commit()
        await db.refresh(data)
        await cache_invalidation(user_id)
    except IntegrityError:
        await db.rollback()
        logger.info(f"failed to edit comment for user_id:{user_id}")
        raise HTTPException(status_code=500, detail="Data Error")
    except Exception as e:
        await db.rollback()
        logger.info("failed to edit comment for user_id:%s, %s", user_id, e)
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
        await cache_invalidation(user_id)
    except IntegrityError:
        await db.rollback()
        logger.error(
            "failed to delete comment, with comment id:%s, for user:%s",
            comment_id,
            user_id,
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(
            "failed to delete comment, with comment id:%s, for user:%s, Error:%s",
            comment_id,
            user_id,
            e,
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
