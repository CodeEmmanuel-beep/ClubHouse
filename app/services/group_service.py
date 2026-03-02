from fastapi import HTTPException
import uuid
from app.models_sql import Group, GroupAdmin, Member, User
from sqlalchemy import select, func
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_
from app.api.v1.models import (
    StandardResponse,
    PaginatedMetadata,
    PaginatedResponse,
    MemberResponse,
    GroupResponse,
)
from sqlalchemy.exc import IntegrityError
from app.log.logger import get_loggers
from app.utils.helpers import generate_signed_urls


logger = get_loggers("group")


async def access(
    group_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    name = payload.get("sub")
    stmt = select(Member).where(Member.user_id == user_id, Member.group_id == group_id)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"unauthorized access attempt by user_id: {user_id}")
        raise HTTPException(
            status_code=403, detail="You are not a member of this group"
        )
    logger.info(f"authorized access by user_id: {user_id} to group_id: {group_id}")
    return {"status": "success", "message": f"welcome {name}"}


async def grouping(profile_picture, name, db, payload, get_supabase):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id, {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    filename = None
    if profile_picture is not None:
        try:
            filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
            file_bytes = await profile_picture.read()
            res = await get_supabase.storage.from_("codeemmanuel").upload(
                filename,
                file_bytes,
                {"content-type": profile_picture.content_type},
            )
            if hasattr(res, "error"):
                logger.error(
                    "Failed to upload profile picture to storage:%s",
                    res["error"]["message"],
                )
                raise HTTPException(
                    status_code=500, detail="Error uploading group profile picture"
                )
            pic = filename
        except Exception as e:
            logger.error("Failed to save profile picture:%s", str(e))
            pic = None
            raise HTTPException(
                status_code=500, detail="Error saving group profile picture"
            )
    else:
        pic = None
    grp = Group(profile_picture=pic, name=name)
    try:
        async with db.begin():
            db.add(grp)
            await db.flush()
            new_admin = GroupAdmin(user_id=user_id, group_id=grp.id, username=username)
            db.add(new_admin)
    except IntegrityError:
        if filename:
            res = await get_supabase.storage.from_("codeemmanuel").remove([filename])
            if hasattr(res, "error"):
                logger.error("failed to remove associated blog file %s", res)
            logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.error("Group creation failed")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        if filename:
            res = await get_supabase.storage.from_("codeemmanuel").remove([filename])
            if hasattr(res, "error"):
                if hasattr(res, "error"):
                    logger.error("failed to remove associated blog file %s", res)
            logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.exception("Group creation failed")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"user_id: {user_id} created group with id: {grp.id}")
    return {"message": "group created"}


async def edit_group(group_id, name, profile_picture, db, payload, get_supabase):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id, {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to edit group with group_id: {group_id}"
        )
        raise HTTPException(status_code=401, detail="not authorized")
    group_stmt = select(Group).where(Group.id == group_id)
    group = (await db.execute(group_stmt)).scalar_one_or_none()
    if not group:
        logger.warning(f"invalid group_id attempt: {group_id} by user_id: {user_id}")
        raise HTTPException(status_code=404, detail="invalid group id")
    if name is not None:
        group.name = name
    filename = None
    old_photo = None
    if profile_picture is not None:
        try:
            filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
            file_bytes = await profile_picture.read()
            res = await get_supabase.storage.from_("codeemmanuel").upload(
                filename,
                file_bytes,
                {"content-type": profile_picture.content_type},
            )
            if hasattr(res, "error"):
                logger.error(
                    "Failed to upload profile picture to storage:%s",
                    res["error"]["message"],
                )
                raise HTTPException(
                    status_code=500, detail="Error uploading group profile picture"
                )
            old_photo = group.profile_picture
            group.profile_picture = filename
        except Exception as e:
            logger.error("Failed to save profile picture:%s", str(e))
            raise HTTPException(
                status_code=500, detail="Error saving group profile picture"
            )
    try:
        await db.commit()
        await db.refresh(group)
        if old_photo:
            res = await get_supabase.storage.from_("codeemmanuel").remove([old_photo])
            if hasattr(res, "error"):
                logger.warning(
                    "Failed to remove old profile picture from storage:%s", res
                )
            else:
                logger.info(
                    "Successfully removed old profile picture from storage:%s",
                    old_photo,
                )
    except IntegrityError:
        await db.rollback()
        if filename:
            res = await get_supabase.storage.from_("codeemmanuel").remove([filename])
            if hasattr(res, "error"):
                logger.error("failed to remove orphaned group profile pics,%s", res)
            logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.error("Group edit failed")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        if filename:
            res = await get_supabase.storage.from_("codeemmanuel").remove([filename])
            if hasattr(res, "error"):
                logger.error("failed to remove orphaned group profile pics,%s", res)
            logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.exception("Group edit failed")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"user_id: {user_id} edited group with id: {group.id}")
    return {"message": "group edited"}


async def add_admin(
    group_id,
    username,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to add admin to group_id: {group_id}"
        )
        raise HTTPException(status_code=401, detail="not authorized")
    user_stmt = select(Member).where(Member.username == username)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        logger.warning(f"member not found: {username}")
        raise HTTPException(status_code=404, detail="user not found")
    new_admin = GroupAdmin(user_id=user.user_id, group_id=group_id, username=username)
    try:
        db.add(new_admin)
        await db.commit()
        await db.refresh(new_admin)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="database error")
    logger.info(f"user_id: {user_id} added admin {username} to group_id: {group_id}")
    return "admin added"


async def add_member(
    group_id,
    username,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=401, detail="not authorized")
    user_stmt = select(User).where(User.username == username)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        logger.warning(f"user not found: {username}")
        raise HTTPException(status_code=404, detail="user not found")
    existing_member = (
        (
            await db.execute(
                select(Member)
                .join(Group)
                .where(Member.username == username, Group.id == group_id)
            )
        )
        .scalars()
        .all()
    )
    if existing_member:
        raise HTTPException(status_code=400, detail="user is already a member")
    new_member = Member(username=username, user_id=user.id, group_id=group_id)
    try:
        db.add(new_member)
        await db.commit()
        await db.refresh(new_member)
    except IntegrityError:
        await db.rollback()
        logger.exception("could not add user %s:", username)
        raise HTTPException(status_code=500, detail="database error")
    except Exception as e:
        await db.rollback()
        logger.exception("could not add user %s:", username)
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"user_id: {user_id} added member {username} to group_id: {group_id}")
    return "username added"


async def admins_list(
    group_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not a valid user")
    stmt = (
        select(GroupAdmin)
        .join(Member, Member.group_id == GroupAdmin.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(Member.user_id == user_id, Member.group_id == group_id),
            )
        )
    ).limit(1)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    stmt = select(GroupAdmin).where(GroupAdmin.group_id == group_id)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(
        f"user_id: {user_id} accessed total admins for group_id: {group_id}, total admins: {total}"
    )
    result = (await db.execute(stmt)).scalars().all()
    admins = [admin.username for admin in result]
    logger.info(f"user_id: {user_id} accessed admins list for group_id: {group_id}")
    return StandardResponse(
        status="success", message="admins list", data={"admins": admins}
    )


async def members_list(group_id, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not a valid user")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    member = await db.execute(
        select(Member).where(Member.group_id == group_id, Member.user_id == user_id)
    )
    member_obj = member.scalar_one_or_none()
    if not member_obj:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="not a member")
    stmt = (
        select(Member)
        .options(selectinload(Member.user))
        .where(Member.group_id == group_id)
    )
    total = (
        await db.execute(
            select(func.count(Member.group_id)).where(Member.group_id == group_id)
        )
    ).scalar() or 0
    logger.info(
        f"user_id: {user_id} accessed total for group_id: {group_id}, total members: {total}"
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        raise HTTPException(status_code=404, detail="members not found")
    filenames = [r.user.profile_picture for r in result if r.user.profile_picture]
    files = await generate_signed_urls(
        request, filenames, context="members profile picture"
    )
    items = []
    for group in result:
        group_members = MemberResponse.model_validate(group)
        filename = group.user.profile_picture if group.user.profile_picture else None
        group_members.member_profile_picture = (
            files.get(filename) if files and filename else None
        )
        items.append(group_members)
    data = PaginatedMetadata[MemberResponse](
        items=items, pagination=PaginatedResponse(page=page, limit=limit, total=total)
    )
    logger.info(f"user_id: {user_id} accessed members list for group_id: {group_id}")
    return StandardResponse(status="success", message="members list", data=data)


async def groups_list(page, limit, db, payload, request):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not a valid user")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    stmt = (
        select(Group)
        .join(Member, Group.id == Member.group_id)
        .where(Member.user_id == user_id)
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"user_id: {user_id} accessed total groups, total: {total}")
    groups = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not groups:
        logger.warning(f"user_id: {user_id} belongs to no group")
        raise HTTPException(status_code=404, detail="you belong to no group")
    filenames = [g.profile_picture for g in groups if g.profile_picture]
    files = await generate_signed_urls(
        request, filenames, context="group profile picture"
    )
    items = []
    for group in groups:
        group_data = GroupResponse.model_validate(group)
        filename = group.profile_picture if group.profile_picture else None
        group_data.profile_picture = files.get(filename) if files and filename else None
        items.append(group_data)
    data = PaginatedMetadata[GroupResponse](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(f"user_id: {user_id} accessed groups list")
    return StandardResponse(status="success", message="groups list", data=data)


async def delete_member(
    group_id,
    username,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="not a valid user")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=401, detail="not authorized")
    stmt = select(Member).where(
        Member.username == username, Member.group_id == group_id
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"invalid username attempt: {username} by user_id: {user_id}")
        raise HTTPException(status_code=404, detail="invalid username")
    try:
        await db.delete(result)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"user_id: {user_id} deleted member {username} from group_id: {group_id}"
    )
    return "member removed"
