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
    Commenter,
    TaskResponse,
    Sharer,
    UserRes,
    PaginatedMetadata,
    PaginatedResponse,
)
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
redis_client = redis.Redis.from_url(settings.REDIS_URL, ssl=True)


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
    offset = (page - 1) * limit
    stmt = (
        select(Blog)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(Blog.user_id == user_id)
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    items = []
    for blog in result:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        items.append(blog_data)
    blogs = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    stmt = (
        select(Share)
        .options(
            selectinload(Share.blog).selectinload(Blog.comments),
            selectinload(Share.user),
        )
        .where(Share.user_id == user_id)
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    items = []
    for share in result:
        share_data = Sharer.model_validate(share)
        share_data.profile_picture = share.user.profile_picture
        share_data.name = share.user.name
        items.append(share_data)
    shar = PaginatedMetadata[Sharer](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    response = {
        "user": users,
        "blogs": blogs,
        "tasks": tasks,
        "shares": shar,
    }
    cached(cache_key, response, ttl=60)
    return {"source": "database", "data": response}


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
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        items.append(blog_data)
    blogs = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    stmt = select(Comment).join(User).where(User.username.in_(username))
    stmt = (
        select(Share)
        .join(User)
        .options(selectinload(Share.blog).selectinload(Blog.comments))
        .where(User.username.in_(username))
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Shares found for user %s", total)
    share_d = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    items = []
    for share in share_d:
        share_data = Sharer.model_validate(share)
        share_data.profile_picture = share.user.profile_picture
        share_data.name = share.user.name
        items.append(share_data)
    shar = PaginatedMetadata[Sharer](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    response = {
        "user": found,
        "blogs": blogs,
        "user_shares": shar,
    }
    cached(cached_key, response, ttl=60)
    return {"source": "database", "data": response}


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
        raise HTTPException(status_code=403, detail="Forbidden access")
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if profile_picture is not None:
        filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
        file_path = os.path.join("images", filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_picture.file, buffer)
        file_url = f"/images/{filename}"
        user.profile_picture = file_url
    else:
        user.profile_picture = None
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
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "profile updated successfully"}


async def delete_profile(
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Forbidden access")
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "profile deleted successfully"}
