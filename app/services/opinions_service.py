from fastapi import HTTPException
from app.api.v1.models import (
    OpinionResponse,
    StandardResponse,
    PaginatedMetadata,
    PaginatedResponse,
    Voting,
)
from app.models_sql import (
    Opinion,
    GroupTask,
    Participant,
    GroupAdmin,
    Group,
    OpinionVote,
    OpinionEnum,
    User,
)
from app.log.logger import get_loggers
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, or_, and_
from app.utils.helpers import generate_signed_urls
from app.utils.reactions_count import vote_type

logger = get_loggers("opinion")


async def create_opinion(
    op,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not authorized")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .join(Group, Group.id == Participant.group_id)
        .where(
            Participant.group_id == op.group_id,
            Participant.username == username,
            Group.id == op.group_id,
            GroupTask.id == op.task_id,
        )
    )
    participant = (await db.execute(stmt)).scalars().all()
    if not participant:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {op.group_id}"
        )
        raise HTTPException(status_code=404, detail="target not found")
    stmt = (
        select(Opinion)
        .join(Group, Group.id == Opinion.group_id)
        .join(GroupTask, GroupTask.id == Opinion.task_id)
        .where(
            Opinion.user_id == user_id,
            GroupTask.id == op.task_id,
            Group.id == op.group_id,
        )
    )
    limit = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(
        f"user_id: {user_id} has {limit} opinions on task_id: {op.task_id} in group_id: {op.group_id}"
    )
    if limit == 2:
        raise HTTPException(
            status_code=400, detail="can not make more than 2 opinions on one task"
        )
    logger.info(
        f"user_id: {user_id} is creating a new opinion on task_id: {op.task_id} in group_id: {op.group_id}"
    )
    new_opinion = Opinion(
        content=op.content,
        user_id=user_id,
        group_id=op.group_id,
        task_id=op.task_id,
    )
    target = await db.get(GroupTask, op.task_id)
    try:
        db.add(new_opinion)
        target.opinion_count = (target.opinion_count or 0) + 1
        await db.commit()
        await db.refresh(new_opinion)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"user_id: {user_id} failed to create opinion on task_id: {op.task_id} in group_id: {op.group_id}"
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"user_id: {user_id} failed to create opinion on task_id: {op.task_id} in group_id: {op.group_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"user_id: {user_id} successfully created opinion id: {new_opinion.id} on task_id: {op.task_id} in group_id: {op.group_id}"
    )
    return {"message": "opinion stated"}


async def fetch(group_id, task_id, page, limit, db, payload, request):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    stmt = (
        select(Participant)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(
                    Participant.username == username, Participant.group_id == group_id
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=403, detail="restricted access")
    stmt = (
        select(Opinion)
        .join(User, User.id == Opinion.user_id)
        .options(selectinload(Opinion.user))
        .where(
            Opinion.task_id == task_id,
            Opinion.group_id == group_id,
            User.is_active == True,
        )
        .order_by(Opinion.vote_count.desc())
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(
        f"{username} is fetching opinions for task_id: {task_id} in group_id: {group_id}, total: {total}"
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        logger.warning(f"{username} unsuccessfully queried opinion")
        raise HTTPException(status_code=404, detail="No target found")
    opinion_ids = [opinion.id for opinion in result]
    vote_map = await vote_type(db, group_id, task_id, opinion_ids)
    filenames = [r.user.profile_picture for r in result if r.user.profile_picture]
    files = await generate_signed_urls(
        request, filenames, context="participants profile picture"
    )
    items = []
    for res in result:
        opinion = OpinionResponse.model_validate(res)
        filename = res.user.profile_picture if res.user.profile_picture else None
        opinion.profile_picture = files.get(filename) if filename else None
        opinion.username = res.user.username
        opinion.votes = vote_map.get(res.id) if res.vote_count > 0 else None
        items.append(opinion)
    data = PaginatedMetadata[OpinionResponse](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(
        f"{username}, fetched {len(items)} opinions for task_id={task_id}, group_id={group_id}"
    )
    return StandardResponse(status="success", message="requested data", data=data)


async def votes(
    group_id,
    task_id,
    opinion_id,
    vote,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    try:
        vote_enum = OpinionEnum(vote)
        logger.info(
            f"user_id: {user_id} is attempting to place a vote: {vote} on opinion_id: {opinion_id}"
        )
    except ValueError:
        logger.warning(f"user_id: {user_id} provided invalid vote type: {vote}")
        raise HTTPException(
            status_code=400, detail="you can only place either an upvote or a downvote"
        )
    stmt = (
        select(Participant)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(
                    Participant.username == username, Participant.group_id == group_id
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=403, detail="restricted access")
    stmt = (
        select(Opinion)
        .join(Group, Group.id == Opinion.group_id)
        .join(GroupTask, GroupTask.id == Opinion.task_id)
        .where(
            Opinion.id == opinion_id,
            GroupTask.id == task_id,
            Group.id == group_id,
        )
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        logger.warning(f"{username} unsuccessfully queried opinion")
        raise HTTPException(status_code=404, detail="No opinion found")
    stmt = (
        select(OpinionVote)
        .join(Group, Group.id == OpinionVote.group_id)
        .join(GroupTask, GroupTask.id == OpinionVote.grouptask_id)
        .where(
            OpinionVote.user_id == user_id,
            OpinionVote.opinion_id == opinion_id,
            GroupTask.id == task_id,
            Group.id == group_id,
        )
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result:
        logger.info(f"user_id: {user_id} is updating vote on opinion_id: {opinion_id}")
        if result.vote == vote_enum:
            await db.delete(result)
            await db.commit()
            target.vote_count = max((target.vote_count or 0) - 1, 0)
            db.add(target)
            await db.commit()
            logger.info(f"user_id: {user_id} removed vote on opinion_id: {opinion_id}")
            return StandardResponse(status="success", message="vote removed", data=vote)
        result.vote = vote_enum
        try:
            await db.commit()
            await db.refresh(result)
        except IntegrityError:
            await db.rollback()
            logger.error(
                f"user_id: {user_id} failed to update vote on opinion_id: {opinion_id}"
            )
            raise HTTPException(status_code=500, detail="internal server error")
        logger.info(f"user_id: {user_id} updated vote on opinion_id: {opinion_id}")
        return StandardResponse(status="success", message="vote updated", data=vote)
    else:
        logger.info(
            f"user_id: {user_id} is placing a new vote on opinion_id: {opinion_id}"
        )
        place = OpinionVote(
            opinion_id=opinion_id,
            group_id=group_id,
            grouptask_id=task_id,
            user_id=user_id,
            vote=vote_enum,
        )
        try:
            db.add(place)
            await db.commit()
            target.vote_count = (target.vote_count or 0) + 1
            db.add(target)
            await db.commit()
            await db.refresh(place)
        except IntegrityError:
            await db.rollback()
            logger.error(
                f"user_id: {user_id} failed to place vote on opinion_id: {opinion_id}"
            )
            raise HTTPException(status_code=500, detail="Database Error")
        except Exception as e:
            await db.rollback()
            logger.exception(
                f"user_id: {user_id} failed to place vote on opinion_id: {opinion_id}"
            )
            raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"user_id: {user_id} successfully placed vote on opinion_id: {opinion_id}"
    )
    return StandardResponse(status="success", message="vote placed", data=vote)


async def delete_one(
    opinion_id,
    group_id,
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"Unauthorized access attempt by user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = (
        select(Participant)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(
                    Participant.username == username, Participant.group_id == group_id
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        raise HTTPException(status_code=403, detail="restricted access")
    stmt = (
        select(Opinion)
        .join(Group, Group.id == Opinion.group_id)
        .join(GroupTask, GroupTask.id == Opinion.task_id)
        .where(
            Opinion.user_id == user_id,
            Opinion.id == opinion_id,
            GroupTask.id == task_id,
            Group.id == group_id,
        )
    )
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(
            f"{username}, tried deleting a nonexistent opinion, opinion id: {opinion_id}"
        )
        raise HTTPException(status_code=404, detail="invalid field")
    target = await db.get(GroupTask, task_id)
    try:
        await db.delete(data)
        target.opinion_count = max((target.opinion_count or 0) - 1, 0)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.error(f"{username} failed to delete opinion id: {opinion_id}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(f"{username} failed to delete opinion id: {opinion_id}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"{username} successfully deleted opinion id: {opinion_id}")
    return {
        "status": "success",
        "message": "deleted opinion",
        "data": {
            "id": data.id,
            "username": username,
            "deleted": "Yes",
        },
    }
