from fastapi import HTTPException
from werkzeug.utils import secure_filename
import os, shutil, uuid
from sqlalchemy import select, func
from app.api.v1.models import (
    Blogger,
    PaginatedMetadata,
    PaginatedResponse,
    StandardResponse,
    ReactionsSummary,
)
from sqlalchemy.exc import IntegrityError
from app.models_sql import Blog, User, React
from datetime import datetime, timezone
from sqlalchemy.orm import selectinload
import json
from app.log.logger import get_loggers
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_loggers("blogs")
os.makedirs("images", exist_ok=True)


async def react_summary(db: AsyncSession, blog_id) -> ReactionsSummary:
    react_count = (
        await db.execute(
            select(React.type, func.count(React.id))
            .where(React.blog_id == blog_id)
            .group_by(React.type)
            .order_by(React.type)
        )
    ).all()
    summary = {
        rtype.name if hasattr(rtype, "name") else rtype: react
        for rtype, react in react_count
    }
    return ReactionsSummary(
        like=summary.get("like", 0),
        love=summary.get("love", 0),
        wow=summary.get("wow", 0),
        haha=summary.get("haha", 0),
        sad=summary.get("sad", 0),
        angry=summary.get("angry", 0),
    )


async def create_blog(db, payload, target, image, details):
    username = payload.get("sub")
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(
            "Author mismatch: token author '%s' vs input author '%s'",
            username,
        )
        raise HTTPException(status_code=403, detail="forbidden entry")
    if image is not None:
        max = 10
        if len(image) > max:
            raise HTTPException(
                status_code=400, detail=f"maximum number of images allowed is {max}"
            )
        uploaded_file = []
        for file in image:
            filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
            file_path = os.path.join("images", filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_url = f"/images/{filename}"
            uploaded_file.append(file_url)
        image = json.dumps(uploaded_file)
    else:
        image = None
    blogs = Blog(
        user_id=user_id,
        image=image,
        target=target,
        details=details,
        time_of_post=datetime.now(timezone.utc),
    )
    try:
        db.add(blogs)
        await db.commit()
        await db.refresh(blogs)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Blog post creation failed for user: {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"Blog post created successfully for user: {username}")
    return {"message": "post successful"}


async def retrieve_all(page, limit, db, payload):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
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
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Total blogs found for '%s': %d", username, total)
    result = await db.scalars(stmt.offset(offset).limit(limit))
    blogs = result.all()
    if not blogs:
        raise HTTPException(status_code=404, detail="No blogs found")
    logger.info("Number of blogs retrieved on this page: %d", len(blogs))
    items = []
    for blog in blogs:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = await react_summary(db, blog.id)
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Paginated data prepared successfully for '%s'", username)
    return StandardResponse(
        status="success", message="below lies all your expressions", data=data
    )


async def filter(
    author,
    target,
    page,
    limit,
    db,
    payload,
):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
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
    if author:
        logger.info(f"Filtering blogs by author: {author}")
        stmt = stmt.where(Blog.user.has(User.name.ilike(f"%{author}%")))
    if target:
        logger.info(f"Filtering blogs by target: {target}")
        stmt = stmt.where(Blog.target.ilike(f"%{target}%"))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Total filtered blogs: %d", total)
    results = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    logger.info("Number of blogs retrieved on this page: %d", len(results))
    items = []
    for blog in results:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = await react_summary(db, blog.id)
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Filtered paginated data prepared successfully for '%s'", username)
    return StandardResponse(
        status="success", message="below lies all your expressions", data=data
    )


async def view_trending(
    sorting,
    page,
    limit,
    db,
    payload,
):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    offset = (page - 1) * limit
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(User.is_active == True)
        .order_by(
            (Blog.comments_count + Blog.share_count + Blog.reacts_count).desc(),
        )
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
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info("Total blogs for '%s': %d", username, total)
    stmt = stmt.offset(offset).limit(limit)
    result = (await db.execute(stmt)).scalars().all()
    logger.info("Number of recent blogs retrieved: %d", len(result))
    items = []
    for blog in result:
        blog_data = Blogger.model_validate(blog)
        blog_data.profile_picture = blog.user.profile_picture
        blog_data.name = blog.user.name
        blog_data.reactions = await react_summary(db, blog.id)
        items.append(blog_data)
    data = PaginatedMetadata[Blogger](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Recent paginated data prepared successfully for '%s'", username)
    return StandardResponse(
        status="success", message="below lies all the recent expressions", data=data
    )


async def fetch_some(
    blog_id,
    db,
    payload,
):
    username = payload.get("sub")
    if not username:
        logger.warning(f"Unauthorized access attempt , username:{username}")
        raise HTTPException(status_code=403, detail="unauthorized access")
    stmt = (
        select(Blog)
        .join(User, User.id == Blog.user_id)
        .options(selectinload(Blog.user), selectinload(Blog.comments))
        .where(Blog.id == blog_id, User.is_active == True)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"No blog found with id {blog_id} for {username}")
        return StandardResponse(status="failure", message="invalid id")
    data = Blogger.model_validate(result)
    data.profile_picture = result.user.profile_picture
    data.name = result.user.name
    data.reactions = await react_summary(db, data.id)
    logger.info(f"Successfully retrieved blog with id {blog_id}: {data}")
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
        stm = select(User).where(User.username == username)
        re = (await db.execute(stm)).scalar_one_or_none()
    except IntegrityError:
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


async def delete_one(blog_id, db, payload):
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
    try:
        await db.delete(data)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.error(f"Failed to delete blog with id {blog_id} for user {username}")
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


async def clear(db, payload):
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
        await db.commit()
    except IntegrityError:
        logger.error(f"Failed to clear blogs for user {username}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"All blogs successfully cleared for user {username}")
    return {"message": "data wiped"}
