from fastapi import HTTPException
from werkzeug.utils import secure_filename
import uuid
from sqlalchemy import select, func
from app.api.v1.models import (
    Blogger,
    PaginatedMetadata,
    PaginatedResponse,
    StandardResponse,
)
from sqlalchemy.exc import IntegrityError
from app.models_sql import Blog, User
from datetime import datetime, timezone
from sqlalchemy.orm import selectinload
import orjson
import asyncio
from app.utils.helpers import (
    generate_signed_urls,
    build_blog_response,
)
from app.utils.reactions_count import blog_react_summary
from app.log.logger import get_loggers
from app.utils.redis import cache_invalidation, cached, caching

logger = get_loggers("blogs")


async def create_blog(db, payload, target, image, details, get_supabase):
    username = payload.get("sub")
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(
            "Author mismatch: token author vs input author '%s'",
            username,
        )
        raise HTTPException(status_code=403, detail="forbidden entry")
    task = []
    uploaded_file = []
    if image is not None:
        max = 10
        if len(image) > max:
            raise HTTPException(
                status_code=400, detail=f"maximum number of images allowed is {max}"
            )
        read_tasks = [file.read() for file in image]
        file_bytes_list = await asyncio.gather(*read_tasks)
        for file, file_bytes in zip(image, file_bytes_list):
            filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
            task.append(
                get_supabase.storage.from_("codeemmanuel").upload(
                    filename, file_bytes, {"content-type": file.content_type}
                )
            )
            uploaded_file.append(filename)
        res = await asyncio.gather(*task, return_exceptions=True)
        for r, uf in zip(res, uploaded_file):
            if isinstance(r, Exception) or hasattr(r, "error"):
                logger.exception("Error uploading blog image: %s", r)
                raise HTTPException(
                    status_code=500, detail="Error uploading blog image"
                )
        logger.info("Saved blog image for user_id=%s: %s", user_id, filename)
        image = orjson.dumps(uploaded_file).decode("utf-8")
    else:
        image = None
    logger.info(f"computing blogs by user, {user_id}")
    if not target and not details and not image:
        logger.warning(f"No content provided for blog post by user: {username}")
        raise HTTPException(status_code=400, detail="provide content to post")
    blogs = Blog(
        user_id=user_id,
        image=image,
        target=target,
        details=details,
        time_of_post=datetime.now(timezone.utc),
    )
    logger.info(f"computed blogs by user, {user_id}")
    try:
        async with db.begin():
            db.add_all([blogs])
        await cache_invalidation(user_id)
    except IntegrityError:
        await db.rollback()
        for upload in uploaded_file:
            if upload:
                cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                    [upload]
                )
                if hasattr(cleaned, "error"):
                    logger.error("failed to remove orphaned blog file %s", cleaned)
                logger.info("Removed orphaned file after rollback: %s", upload)
        logger.error(
            f"Blog post creation failed due to intergrity error for user: {user_id}"
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        for upload in uploaded_file:
            if upload:
                cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                    [upload]
                )
                if hasattr(cleaned, "error"):
                    logger.error("failed to remove orphaned blog file %s", cleaned)
                logger.info("Removed orphaned file after rollback: %s", upload)
        logger.exception(f"Blog post creation failed for user: {user_id}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Blog post created successfully for user: {username}")
    return {"message": "post successful"}


async def retrieve_all(page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt , user_id:{user_id}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_key = f"blog_url:{page}:{limit}"
    cached_data = await caching(cache_key)
    if cached_data:
        logger.info(f"Cache hit for user_id: page: {page}, limit: {limit}")
        profile_pic_map = cached_data.get("profile_picture", {})
        file_map = cached_data.get("blog_image", {})
    stmt = (
        select(Blog)
        .join(Blog.user)
        .options(selectinload(Blog.user))
        .where(User.is_active == True)
        .order_by(
            Blog.time_of_post.desc(),
            (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
        )
    )
    result = await db.scalars(stmt.offset(offset).limit(limit))
    blogs = result.all()
    if not blogs:
        raise HTTPException(status_code=404, detail="No blogs found")
    logger.info("Number of blogs retrieved on this page: %d", len(blogs))
    blog_ids = [b.id for b in blogs]
    sub_total, blog_reaction_map = await asyncio.gather(
        db.execute(
            select(func.count(Blog.id)).join(Blog.user).where(User.is_active == True)
        ),
        blog_react_summary(db, blog_ids),
    )
    total = sub_total.scalar() or 0
    logger.info("Total blogs found for '%s': %d", username, total)
    filenames = []
    capture = []
    if not cached_data:
        filenames = [f for b in blogs if b.image for f in (orjson.loads(b.image)) if f]
        capture = [b.user.profile_picture for b in blogs if b.user.profile_picture]
        file_map, profile_pic_map = await asyncio.gather(
            generate_signed_urls(request, filenames, context="blog image"),
            generate_signed_urls(request, capture, context="blogger profile picture"),
            return_exceptions=False,
        )
        url = {"profile_picture": profile_pic_map, "blog_image": file_map}
        await cached(cache_key, url, ttl=2000)
    items = []
    for blog in blogs:
        blog_data = build_blog_response(
            blog, profile_pic_map, file_map, blog_reaction_map
        )
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Paginated data prepared successfully for '%s'", username)
    return StandardResponse(status="success", message="expressions", data=data)


async def filter(author, target, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_data = f"blog_url:{author or ''}:{target or ''}:{page}:{limit}"
    cached_data = await caching(cache_data)
    if cached_data:
        logger.info(f"Cache hit for user_id: page: {page}, limit: {limit}")
        profile_pic_map = cached_data.get("profile_picture", {})
        file_map = cached_data.get("blog_image", {})
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user))
        .where(User.is_active == True)
        .order_by(
            Blog.time_of_post.desc(),
            (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
        )
    )
    if author:
        logger.info(f"Filtering blogs by author: {author}")
        stmt = stmt.where(Blog.user.has(User.name.ilike(f"%{author}%")))
    if target:
        logger.info(f"Filtering blogs by target: {target}")
        stmt = stmt.where(Blog.target.ilike(f"%{target}%"))
    blogs = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not blogs:
        raise HTTPException(status_code=404, detail="No blogs found")
    logger.info("Number of blogs retrieved on this page: %d", len(blogs))
    blog_ids = [b.id for b in blogs]
    sub_total, blog_reaction_map = await asyncio.gather(
        db.execute(
            select(func.count(Blog.id)).join(Blog.user).where(User.is_active == True)
        ),
        blog_react_summary(db, blog_ids),
    )
    total = sub_total.scalar() or 0
    logger.info("Total blogs found for '%s': %d", username, total)
    capture = []
    filenames = []
    if not cached_data:
        capture = [b.user.profile_picture for b in blogs if b.user.profile_picture]
        filenames = [f for b in blogs if b.image for f in (orjson.loads(b.image)) if f]
        file_map, profile_pic_map = await asyncio.gather(
            generate_signed_urls(request, filenames, context="blog image"),
            generate_signed_urls(request, capture, context="blogger profile picture"),
        )
        url = {"profile_picture": profile_pic_map, "blog_image": file_map}
        await cached(cache_data, url, ttl=1000)
    items = []
    for blog in blogs:
        blog_data = build_blog_response(
            blog, profile_pic_map, file_map, blog_reaction_map
        )
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Filtered paginated data prepared successfully for '%s'", username)
    return StandardResponse(status="success", message="expressions", data=data)


async def view_trending(sorting, page, limit, db, payload, request):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    cache_data = f"blog_url:{sorting}:{page}:{limit}"
    cached_data = await caching(cache_data)
    if cached_data:
        logger.info(f"Cache hit for user_id: page: {page}, limit: {limit}")
        profile_pic_map = cached_data.get("profile_picture", {})
        file_map = cached_data.get("blog_image", {})
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user))
        .where(User.is_active == True)
    )
    if sorting == "recent":
        logger.info(f"Sorting blogs by recent for user: {username}")
        stmt = stmt.order_by(Blog.time_of_post.desc())
    if sorting == "popular":
        logger.info(f"Sorting blogs by popular for user: {username}")
        stmt = stmt.order_by(
            Blog.comments_count.desc(),
            Blog.share_count.desc(),
            Blog.reacts_count.desc(),
        )
    blogs = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    logger.info("Number of recent blogs retrieved: %d", len(blogs))
    blog_ids = [b.id for b in blogs]
    sub_total, blog_reaction_map = await asyncio.gather(
        db.execute(
            select(func.count(Blog.id)).join(Blog.user).where(User.is_active == True)
        ),
        blog_react_summary(db, blog_ids),
    )
    total = sub_total.scalar() or 0
    logger.info("Total blogs found for '%s': %d", username, total)
    capture = []
    filenames = []
    if not cached_data:
        capture = [b.user.profile_picture for b in blogs if b.user.profile_picture]
        filenames = [f for b in blogs if b.image for f in orjson.loads(b.image) if f]
        file_map, profile_pic_map = await asyncio.gather(
            generate_signed_urls(request, filenames, context="blog image"),
            generate_signed_urls(request, capture, context="blogger profile picture"),
        )
        url = {"profile_picture": profile_pic_map, "blog_image": file_map}
        await cached(cache_data, url, ttl=1000)
    items = []
    for blog in blogs:
        blog_data = build_blog_response(
            blog, profile_pic_map, file_map, blog_reaction_map
        )
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Recent paginated data prepared successfully for '%s'", username)
    return StandardResponse(status="success", message="expressions", data=data)


async def fetch_some(blog_id, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    cache_key = f"blog_url:{blog_id}"
    cached_data = await caching(cache_key)
    if cached_data:
        logger.info(f"Cache hit for blog_id: {blog_id}")
        profile_pic_map = cached_data.get("profile_picture", {})
        file_map = cached_data.get("blog_image", {})
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user))
        .where(Blog.id == blog_id, User.is_active == True)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"No blog found with id {blog_id} for {username}")
        raise HTTPException(status_code=400, detail="invalid id")
    blog_reaction_map = await blog_react_summary(db, result.id)
    filename = []
    capture = []
    if not cached_data:
        filename = orjson.loads(result.image) if result.image else []
        capture = result.user.profile_picture if result.user.profile_picture else []
        file_map, profile_pic_map = await asyncio.gather(
            generate_signed_urls(request, filename, context="blog image"),
            generate_signed_urls(request, capture, context="blogger profile picture"),
        )
        url = {"profile_picture": profile_pic_map, "blog_image": file_map}
        await cached(cache_key, url, ttl=200)
    data = build_blog_response(result, profile_pic_map, file_map, blog_reaction_map)
    logger.info(f"Successfully retrieved blog with id {blog_id}: {username}")
    return StandardResponse(status="success", message="requested data", data=data)


async def change(
    blog_id,
    target,
    details,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    stmt = select(Blog).where(Blog.user_id == user_id, Blog.id == blog_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(f"No blog found with id {blog_id} for {username}")
        raise HTTPException(status_code=400, detail="invalid blog_id")
    if target:
        logger.info(f"Updating target for blog id {blog_id} to {target}")
        data.target = target
    if details:
        logger.info(f"Updating details for blog id {blog_id}")
        data.details = details
    data.time_of_post = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(data)
        await cache_invalidation(user_id)
        stm = select(User).where(User.username == username)
        re = (await db.execute(stm)).scalar_one_or_none()
    except IntegrityError:
        await db.rollback()
        logger.error(f"Blog update failed for blog id {blog_id} by user {username}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception:
        await db.rollback()
        logger.error(f"Blog update failed for blog id {blog_id} by user {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Blog with id {blog_id} successfully updated by user {username}")
    return {
        "status": "success",
        "message": "blog successfully updated",
        "data": {
            "id": data.id,
            "author": re.name,
            "title": data.target,
            "content": data.details,
            "nationality": re.nationality,
            "commencement": data.time_of_post,
        },
    }


async def delete_one(blog_id, db, payload, get_supabase):
    username = payload.get("sub")
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    stmt = select(Blog).where(Blog.user_id == user_id, Blog.id == blog_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(
            f"No blog found to delete with id {blog_id} for author {username}"
        )
        return {"status": "no data", "message": "invalid field"}
    filename = data.image if data.image else None
    try:
        await db.delete(data)
        if filename:
            try:
                paths = orjson.loads(filename)
                if isinstance(paths, list):
                    for path in paths:
                        cleaned = await get_supabase.storage.from_(
                            "codeemmanuel"
                        ).remove([path])
                        if hasattr(cleaned, "error"):
                            logger.error(
                                "failed to remove associated blog file %s", cleaned
                            )
                            raise HTTPException(
                                status_code=500, detail="internal server error"
                            )
                        logger.info(
                            "Removed associated blog file after deletion: %s", path
                        )
                else:
                    cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                        [paths]
                    )
                    if hasattr(cleaned, "error"):
                        logger.error(
                            "failed to remove associated blog file %s", cleaned
                        )
                        raise HTTPException(
                            status_code=500, detail="internal server error"
                        )
                    logger.info(
                        "Removed associated blog file after deletion: %s", paths
                    )
            except orjson.JSONDecodeError:
                cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                    [filename]
                )
                if hasattr(cleaned, "error"):
                    logger.error("failed to remove associated file %s", cleaned)
                    raise HTTPException(status_code=500, detail="internal server error")
                logger.info("Removed associated blog file after deletion: %s", filename)
        await db.commit()
        await cache_invalidation(user_id)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Failed to delete blog with id {blog_id} for user {username}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception:
        await db.rollback()
        logger.exception(
            "Failed to delete blog with id %s for user %s:", blog_id, username
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Blog with id {blog_id} successfully deleted by user {username}")
    return {
        "status": "success",
        "message": "blog successfully deleted",
        "data": {
            "id": data.id,
            "username": username,
            "title": data.details,
        },
    }


async def clear(db, payload, get_supabase):
    username = payload.get("sub")
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    stmt = select(Blog).where(Blog.user_id == user_id)
    data = (await db.execute(stmt)).scalars().all()
    if not data:
        logger.warning(f"No blogs found to clear for {username}")
        return {"message:": "no available data"}
    try:
        for item in data:
            await db.delete(item)
            if item.image:
                try:
                    paths = orjson.loads(item.image)
                    if isinstance(paths, list):
                        for path in paths:
                            cleaned = await get_supabase.storage.from_(
                                "codeemmanuel"
                            ).remove([path])
                            if hasattr(cleaned, "error"):
                                logger.error(
                                    "failed to remove associated blog file %s", cleaned
                                )
                                raise HTTPException(
                                    status_code=500, detail="internal server error"
                                )
                            logger.info(
                                "Removed associated blog file after deletion: %s",
                                path,
                            )
                    else:
                        cleaned = await get_supabase.storage.from_(
                            "codeemmanuel"
                        ).remove([paths])
                        if hasattr(cleaned, "error"):
                            logger.error(
                                "failed to remove associated blog file %s", cleaned
                            )
                            raise HTTPException(
                                status_code=500, detail="internal server error"
                            )
                        logger.info(
                            "Removed associated blog file after deletion: %s", paths
                        )
                except orjson.JSONDecodeError:
                    cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                        [item.image]
                    )
                    if hasattr(cleaned, "error"):
                        logger.error(
                            "failed to remove associated blog file %s", cleaned
                        )
                        raise HTTPException(
                            status_code=500, detail="internal server error"
                        )
                    logger.info(
                        "Removed associated blog file after deletion: %s", item.image
                    )
        await db.commit()
        await cache_invalidation(user_id)
    except IntegrityError:
        logger.error(f"Failed to clear blogs for user {username}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception:
        logger.exception("Failed to clear blogs for user %s", username)
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"All blogs successfully cleared for user {username}")
    return {"message": "data wiped"}
