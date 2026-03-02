from app.models_sql import User
from app.api.v1.models import (
    UserResponse,
    UserRes,
    PaginatedMetadata,
    PaginatedResponse,
    StandardResponse,
)
import uuid
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy import and_, select, func, or_
from app.log.logger import get_loggers
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.utils.redis import caching, cached, cache_invalidation
import tracemalloc
from app.utils.helpers import (
    generate_signed_urls,
    generate_signed_url,
)

tracemalloc.start()


logger = get_loggers("profile")


async def view(db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning("User ID missing in token payload")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    stmt = select(User).where(User.is_active == True, User.username == username)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        logger.warning(f"User not found: username={username}")
        raise HTTPException(status_code=404, detail="User not found")
    users = UserResponse.model_validate(user)
    users.profile_picture = (
        await generate_signed_url(
            request, user.profile_picture, context="user's profile picture"
        )
        if user.profile_picture
        else None
    )
    return StandardResponse(status="success", message="database", data=users)


async def other_users(name, page, limit, db, payload, request):
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    user_id = payload.get("user_id")
    if user_id is None:
        logger.warning("Unauthorized access attempt without username in token")
        raise HTTPException(status_code=403, detail="not a user")
    cached_key = f"profile:{name}:{page}:{limit}"
    cache_d = await caching(cached_key)
    if cache_d:
        logger.info(f"Cache hit for search with key: {cached_key}")
        return StandardResponse(**cache_d)
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
    filenames = [s.profile_picture for s in search if s.profile_picture]
    files = await generate_signed_urls(
        request, filenames, context="blog(search) profile picture"
    )
    if not search:
        logger.warning(f"User search yielded no results for name: {name}")
        raise HTTPException(status_code=404, detail="user not found")
    logger.info("Found user with name=%s", name)
    items = []
    for s in search:
        search_data = UserRes.model_validate(s)
        filename = s.profile_picture if s.profile_picture else None
        search_data.profile_picture = (
            files.get(filename) if files and filename else None
        )
        items.append(search_data)
    found = PaginatedMetadata[UserRes](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    response = {"users": found}
    full_response = StandardResponse(
        status="success", message="database", data=response
    )
    await cached(cached_key, full_response, ttl=600)
    return full_response


async def profile(
    profile_picture,
    name,
    nationality,
    address,
    age,
    phone_number,
    db,
    payload,
    get_supabase,
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
    old_filename = None
    filename = None
    if profile_picture is not None:
        try:
            file_bytes = await profile_picture.read()
            filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
            res = await get_supabase.storage.from_("codeemmanuel").upload(
                filename,
                file_bytes,
                {"content-type": profile_picture.content_type},
            )
            if hasattr(res, "error"):
                logger.error(
                    "Failed to upload profile picture for user_id=%s: %s", user_id, res
                )
                raise HTTPException(
                    status_code=500, detail="Error uploading profile picture"
                )
            old_filename = user.profile_picture
            user.profile_picture = filename
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
        if filename and old_filename:
            cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                [old_filename]
            )
            if hasattr(cleaned, "error"):
                logger.error(
                    "Failed to remove old profile picture for user_id=%s: %s",
                    user_id,
                    cleaned,
                )
            else:
                logger.info(
                    "Removed old profile picture for user_id=%s: %s",
                    user_id,
                    old_filename,
                )
    except IntegrityError as e:
        await db.rollback()
        if filename:
            cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleaned, "error"):
                logger.error(
                    "Failed to remove orphaned file after rollback for user_id=%s: %s",
                    user_id,
                    cleaned,
                )
            else:
                logger.warning("removed orphaned file after rollback:%s", filename)
        logger.error(
            "IntegrityError while updating profile for user_id=%s: %s", user_id, str(e)
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        if filename:
            cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleaned, "error"):
                logger.error(
                    "Failed to remove orphaned file after rollback for user_id=%s: %s",
                    user_id,
                    cleaned,
                )
            else:
                logger.warning("removed orphaned file after rollback:%s", filename)
        logger.error("Error while updating profile for user_id=%s: %s", user_id, str(e))
        raise HTTPException(status_code=500, detail="internal server error")
    await cache_invalidation(user_id)
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
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(
            "Internal server error while updating profile for user_id=%s: %s",
            user_id,
            str(e),
        )
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "profile deleted successfully"}
