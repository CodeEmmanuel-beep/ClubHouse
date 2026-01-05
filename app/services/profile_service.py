from app.models_sql import (
    Blog,
    User,
    Comment,
    Task,
    Share,
)
from app.api.v1.models import (
    Blogger,
    UserResponse,
    CommentResponse,
    TaskResponse,
    Sharer,
    UserRes,
    PaginatedMetadata,
    PaginatedResponse,
    StandardResponse,
)
from app.services.comment_service import react_summary
from app.services.blog_service import react_sum, blog_react_summary
import uuid, os, shutil
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
from app.log.logger import get_loggers
import redis
import json, os
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
import tracemalloc

tracemalloc.start()


logger = get_loggers("profile")

redis_url = settings.REDIS_URL
if redis_url.startswith("rediss://"):
    redis_client = redis.from_url(
        redis_url,
        ssl_cert_reqs=None,
        decode_responses=True,
    )
else:
    redis_client = redis.from_url(redis_url, decode_responses=True)
try:
    print(redis_client.ping())
except Exception as e:
    print(f"Redis connection failed: {e}")


def caching(key: str):
    value = redis_client.get(key)
    if value:
        return json.loads(value)
    return None


def cached(key: str, my_dict: dict, ttl=60):
    my_dict = {"key": "value"}
    redis_client.set(key, json.dumps(my_dict), ex=ttl)


async def helper_f(
    db: AsyncSession, model, schema, user_id: int, page: int, limit: int
):
    offset = (page - 1) * limit
    total_s = select(func.count()).select_from(model).where(model.user_id == user_id)
    total = (await db.execute(total_s)).scalar() or 0
    stmt = select(model).where(model.user_id == user_id).offset(offset).limit(limit)
    result = (await db.execute(stmt)).scalars().all()
    items = [schema.model_validate(item) for item in result]
    return PaginatedMetadata[schema](
        items=items, pagination=PaginatedResponse(page=page, limit=limit, total=total)
    )


async def view(
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning("User ID missing in token payload")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    cache_key = f"profile:{user_id}:{page}:{limit}"
    cache_d = caching(cache_key)
    if cache_d:
        logger.info(f"Cache hit for user profile with key: {cache_key}")
        return {"source": "cached", "data": cache_d}
    stmt = select(User).where(User.is_active == True, User.username == username)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        logger.warning(f"User not found: username={username}")
        raise HTTPException(status_code=404, detail="User not found")
    users = UserResponse.model_validate(user)
    tasks = await helper_f(db, Task, TaskResponse, user_id, page, limit)
    logger.info("Fetched %d tasks for user_id=%s", len(tasks.items), user_id)
    offset = (page - 1) * limit
    stmt = (
        select(Blog)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(Blog.user_id == user_id)
    ).order_by(
        Blog.time_of_post.desc(),
        (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
    )
    blogs = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    items = []
    for blog in blogs:
        comment = (
            (
                await db.execute(
                    select(Comment)
                    .join(User, User.id == Comment.user_id)
                    .options(selectinload(Comment.user))
                    .where(User.is_active == True, Comment.blog_id == blog.id)
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
        logger.info("Fetched %d recent comments", len(comment))
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
            comment_response.append(comment_data)
        blog_ids = [b.id for b in blogs]
        blog_reaction_map = await blog_react_summary(db, blog_ids)
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = (
            blog_reaction_map.get(blog.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = comment_response
        items.append(blog_data)
    blog_service = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
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
    share_result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Fetched %d shares (total=%d)", len(share_result), total)
    items = []
    for sh in share_result:
        stmt = (
            select(Blog)
            .join(User, User.id == Blog.user_id)
            .options(selectinload(Blog.user), selectinload(Blog.comments))
            .where(User.is_active == True, Blog.id == sh.blog_id)
            .order_by(
                Blog.time_of_post.desc(),
                (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
            )
        )
        result = await db.execute(stmt)
        logger.info(f"Fetching blogs for active users for user: {user_id}")
        blogs = result.scalar_one_or_none()
        blog_data = Blogger.model_validate(blogs)
        blog_data.profile_picture = blogs.user.profile_picture
        blog_data.name = blogs.user.name
        blog_data.reactions = (
            await react_sum(db, blogs.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = comment_response
        share_data = Sharer.model_validate(sh)
        share_data.profile_picture = sh.user.profile_picture
        share_data.name = sh.user.name
        share_data.blog = blog_data
        items.append(share_data)
    shares = PaginatedMetadata[Sharer](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    response = {
        "user": users,
        "blogs": blog_service,
        "tasks": tasks,
        "shares": shares,
    }
    cached(cache_key, response, ttl=3600)
    logger.info("Response built and cached for key=%s", cache_key)
    return StandardResponse(status="success", message="database", data=response)


async def other_users(
    name,
    page,
    limit,
    db,
    payload,
):
    offset = (page - 1) * limit
    user_id = payload.get("user_id")
    if user_id is None:
        logger.warning("Unauthorized access attempt without username in token")
        raise HTTPException(status_code=403, detail="not a user")
    cached_key = f"profile: {name}:{page}:{limit}"
    cache_d = caching(cached_key)
    if cache_d:
        logger.info(f"Cache hit for search with key: {cached_key}")
        return {"source": "cache", "data": cache_d}
    stmt = (
        select(User)
        .options(
            selectinload(User.blogs),
            selectinload(User.comments),
            selectinload(User.shares),
        )
        .where(
            or_(
                and_(User.name.ilike(f"%{name}%"), User.is_active == True),
                and_(User.username.ilike(f"%{name}%"), User.is_active == True),
            )
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"Total users found for search with name: {name} is {total}")
    search = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not search:
        logger.warning(f"User search yielded no results for name: {name}")
        raise HTTPException(status_code=404, detail="user not found")
    logger.info("Found user with id=%s", name)
    found = PaginatedMetadata[UserRes](
        items=[UserRes.model_validate(item) for item in search],
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    username = [u.username for u in search]
    data = (
        select(Blog)
        .join(User)
        .options(selectinload(Blog.comments), selectinload(Blog.user))
        .where(User.username.in_(username))
        .order_by(Blog.time_of_post.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(data.subquery()))
    ).scalar() or 0
    logger.info("Blogs found for users %s", total)
    blogs = (await db.execute(data.offset(offset).limit(limit))).scalars().all()
    items = []
    for blog in blogs:
        comment = (
            (
                await db.execute(
                    select(Comment)
                    .join(User, User.id == Comment.user_id)
                    .options(selectinload(Comment.user))
                    .where(User.is_active == True, Comment.blog_id == blog.id)
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
        logger.info("Fetched %d recent comments", len(comment))
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
            comment_response.append(comment_data)
        blog_ids = [b.id for b in blogs]
        blog_reaction_map = await blog_react_summary(db, blog_ids)
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = (
            blog_reaction_map.get(blog.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = comment_response
        items.append(blog_data)
    blog_service = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    stmt = (
        (
            select(Share)
            .join(User, User.id == Share.user_id)
            .options(
                selectinload(Share.user),
                selectinload(Share.blog).selectinload(Blog.comments),
            )
        )
        .where(User.is_active == True, User.username.in_(username))
        .order_by(Share.time_of_share.desc())
    )
    share_result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Fetched %d shares (total=%d)", len(share_result), total)
    items = []
    for sh in share_result:
        stmt = (
            select(Blog)
            .join(User, User.id == Blog.user_id)
            .options(selectinload(Blog.user), selectinload(Blog.comments))
            .where(User.is_active == True, Blog.id == sh.blog_id)
            .order_by(
                Blog.time_of_post.desc(),
                (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
            )
        )
        result = await db.execute(stmt)
        logger.info(f"Fetching blogs for active users for user: {user_id}")
        blogs = result.scalar_one_or_none()
        comment = (
            (
                await db.execute(
                    select(Comment)
                    .join(User, User.id == Comment.user_id)
                    .options(selectinload(Comment.user))
                    .where(User.is_active == True, Comment.blog_id == sh.blog_id)
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
            comment_response.append(comment_data)
        blog_data = Blogger.model_validate(blogs)
        blog_data.profile_picture = blogs.user.profile_picture
        blog_data.name = blogs.user.name
        blog_data.reactions = (
            await react_sum(db, blogs.id) if blog_data.reacts_count > 0 else None
        )
        blog_data.comments = comment_response
        share_data = Sharer.model_validate(sh)
        share_data.profile_picture = sh.user.profile_picture
        share_data.name = sh.user.name
        share_data.blog = blog_data
        items.append(share_data)
        logger.debug(items)
    shares = PaginatedMetadata[Sharer](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    response = {
        "user": found,
        "blogs": blog_service,
        "user_shares": shares,
    }
    cached(cached_key, response, ttl=600)
    logger.info("Response built and cached for key=%s", cached_key)
    return StandardResponse(status="success", message="database", data=response)


async def profile(
    profile_picture,
    name,
    nationality,
    address,
    age,
    phone_number,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Forbidden access attempt: missing user_id in payload")
        raise HTTPException(status_code=403, detail="Forbidden access")
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        logger.warning("User not found: user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    file_path = None
    file_url = None
    if profile_picture is not None:
        try:
            filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
            file_path = os.path.join("images", filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(profile_picture.file, buffer)
            file_url = f"/images/{filename}"
            user.profile_picture = file_url
        except Exception as e:
            logger.error(
                "Failed to save profile picture for user_id=%s: %s", user_id, str(e)
            )
            raise HTTPException(status_code=500, detail="Error saving profile picture")
    if nationality is not None:
        user.nationality = nationality
    if name is not None:
        user.name = name
    if address is not None:
        user.address = address
    if age is not None:
        user.age = age
    if phone_number is not None:
        user.phone_number = phone_number
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as e:
        await db.rollback()
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.warning("removed orphaned file after rollback:%s", file_path)
        logger.error(
            "IntegrityError while updating profile for user_id=%s: %s", user_id, str(e)
        )
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "profile updated successfully"}


async def delete_profile(
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning("Forbidden access attempt: missing user_id in payload")
        raise HTTPException(status_code=403, detail="Forbidden access")
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        logger.warning("User not found: user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError as e:
        await db.rollback()
        logger.error(
            "IntegrityError while updating profile for user_id=%s: %s", user_id, str(e)
        )
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "profile deleted successfully"}
