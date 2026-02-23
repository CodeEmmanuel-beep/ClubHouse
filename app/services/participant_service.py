from sqlalchemy.orm import selectinload

from app.models_sql import Participant, GroupAdmin, GroupTask, Member
from sqlalchemy import func, select, or_, and_
from fastapi import HTTPException
from app.api.v1.models import (
    PaginatedResponse,
    StandardResponse,
    PaginatedMetadata,
    ParticipantResponse,
)
from sqlalchemy.exc import IntegrityError
from app.log.logger import get_loggers

logger = get_loggers("participants")


async def add_participant(
    participate,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not authorized")
    stmt = select(GroupAdmin).where(
        GroupAdmin.group_id == participate.group_id, GroupAdmin.user_id == user_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {participate.group_id}"
        )
        raise HTTPException(status_code=403, detail="you are not the admin")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            Participant.username == participate.username,
            GroupTask.id == participate.grouptask_id,
        )
    )
    existing_participant = (await db.execute(stmt)).scalar_one_or_none()
    if existing_participant:
        logger.warning(
            f"participant already exists with username: {participate.username}"
        )
        raise HTTPException(status_code=400, detail="participant already exists")
    stmt = select(GroupTask).where(GroupTask.id == participate.grouptask_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        logger.warning(f"task not found for grouptask_id: {participate.grouptask_id}")
        raise HTTPException(status_code=404, detail="task not found")
    mark = Participant(
        username=participate.username,
        assignment=participate.assignment,
        amount_levied=participate.amount_levied,
        group_id=participate.group_id,
    )
    stmt = select(Member).where(
        Member.group_id == participate.group_id, Member.username == mark.username
    )
    member = (await db.execute(stmt)).scalar_one_or_none()
    if not member:
        logger.warning(f"username not found in group_id: {participate.group_id}")
        raise HTTPException(status_code=404, detail="username not found in this group")
    try:
        mark.group_tasks.append(task)
        db.add(mark)
        await db.commit()
        await db.refresh(mark)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Failed to add participant with username: {participate.username} to group_id: {participate.group_id}"
        )
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(
            f"Failed to add participant with username: {participate.username} to group_id: {participate.group_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"participant {participate.username} added to group_id: {participate.group_id} by user_id: {user_id}"
    )
    return {"status": "success", "message": "participant successfully added"}


async def get_all(
    group_id,
    grouptask_id,
    db,
    page,
    limit,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="not authorized")
    offset = (page - 1) * limit
    if page <= 0 or limit <= 0:
        raise HTTPException(
            status_code=400, detail="page and limit should be atleast one"
        )
    participant_task_id = (
        (
            await db.execute(
                select(Participant)
                .join(Participant.group_tasks)
                .options(selectinload(Participant.group_tasks))
            )
        )
        .scalars()
        .all()
    )
    verify_stmt = (
        await db.execute(
            select(GroupAdmin)
            .join(GroupAdmin.group)
            .where(
                GroupAdmin.group_id == group_id,
                GroupAdmin.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    stmt = (
        select(Participant)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .join(GroupTask, GroupTask.group_id == GroupAdmin.group_id)
    ).where(
        GroupTask.id.in_(
            [task.id for p in participant_task_id for task in p.group_tasks]
        ),
        GroupTask.id == grouptask_id,
        GroupAdmin.user_id == user_id,
        GroupAdmin.group_id == group_id,
        GroupTask.group_id == group_id,
    )
    admin = (
        (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
        if verify_stmt
        else None
    )
    logger.info(
        f"participants count retrieved by admin: {group_id} and grouptask_id: {grouptask_id}, total: {len(admin) if admin else 0}"
    )
    participant = None
    if not admin or admin is None:
        verify_stmt = (
            await db.execute(
                select(Participant)
                .join(Participant.group_tasks)
                .where(
                    Participant.group_id == group_id,
                    Participant.username == username,
                )
            )
        ).scalar_one_or_none()
        if not verify_stmt:
            logger.warning(
                f"user_id: {user_id} is not a participant in group_id: {group_id} for grouptask_id: {grouptask_id}"
            )
            raise HTTPException(
                status_code=403, detail=" this target has no participants"
            )
        stmt = (
            select(Participant)
            .join(Participant.group_tasks)
            .where(
                Participant.group_id == group_id,
                GroupTask.id.in_(
                    [task.id for p in participant_task_id for task in p.group_tasks]
                ),
                GroupTask.id == grouptask_id,
                GroupTask.group_id == group_id,
            )
        )
        participant = (
            (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
        )
    if not admin and not participant:
        logger.warning(
            f"user_id: {user_id} is not a participant in group_id: {group_id} for grouptask_id: {grouptask_id}"
        )
        raise HTTPException(status_code=403, detail="not a participant")
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(
        "participants count retrieved for group_id: %s and grouptask_id: %s, total: %s",
        group_id,
        grouptask_id,
        total,
    )
    part = admin if admin else participant
    data = PaginatedMetadata[ParticipantResponse](
        items=[ParticipantResponse.model_validate(p) for p in part],
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(
        f"participants data prepared for group_id: {group_id} and grouptask_id: {grouptask_id}"
    )
    return StandardResponse(
        status="success", message="participants retrieved", data=data
    )


async def mark_assignment_complete(
    group_id,
    grouptask_id,
    participant_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(GroupAdmin).where(
        GroupAdmin.group_id == group_id, GroupAdmin.user_id == user_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(f"{username}, tried marking an assignment as complete, id")
        raise HTTPException(status_code=404, detail="not authorized")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            Participant.group_id == group_id,
            Participant.id == participant_id,
            GroupTask.id == grouptask_id,
            GroupTask.group_id == group_id,
        )
    )
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"participant not found with id: {participant_id} in group_id: {group_id} for grouptask_id: {grouptask_id}"
        )
        raise HTTPException(status_code=404, detail="invalid task id")
    participant.assignment_complete = True
    logger.info(
        f"{username} successfully marked assignment with  id '{participant_id}' as complete"
    )
    try:
        await db.commit()
        await db.refresh(participant)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Integrity error by {username}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(f"internal server  error by {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"{username} successfully marked assignment with id '{participant_id}' as complete"
    )
    return {
        "status": "success",
        "message": "completed assignment",
        "data": {
            "id": participant_id,
            "username": participant.username,
            "completed": "Yes",
        },
    }


async def completed_assignments(
    group_id,
    group_task_id,
    page,
    limit,
    db,
    payload,
):
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
        .join(Participant.group_tasks)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(
                    GroupAdmin.user_id == user_id,
                    GroupAdmin.group_id == group_id,
                    GroupTask.id == group_task_id,
                ),
                and_(
                    Participant.group_id == group_id,
                    GroupTask.id == group_task_id,
                    Participant.username == username,
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"user_id: {user_id} is not a participant in group_id: {group_id} for grouptask_id: {group_task_id}"
        )
        raise HTTPException(status_code=403, detail="not a participant")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            GroupTask.group_id == group_id,
            GroupTask.id == group_task_id,
            Participant.assignment_complete.is_(True),
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(
        f"{username} successfully queried completed assignments, total: {total}"
    )
    data = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not data:
        logger.warning(
            f"{username} has no completed assignments in group_id: {group_id} for grouptask_id: {group_task_id}"
        )
        raise HTTPException(
            status_code=404, detail="no participant has completed their assignment"
        )
    check = PaginatedMetadata[ParticipantResponse](
        items=[ParticipantResponse.model_validate(part) for part in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    logger.info(f"{username} successfully queried completed assignments")
    return StandardResponse(
        status="success",
        message="task executed",
        data=check,
    )


async def mark_levy(
    group_id,
    grouptask_id,
    participant_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(GroupAdmin).where(
        GroupAdmin.group_id == group_id, GroupAdmin.user_id == user_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"{username}, tried marking an assignment as complete, id {participant_id} in group_id: {group_id} for grouptask_id: {grouptask_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            Participant.group_id == group_id,
            Participant.id == participant_id,
            GroupTask.id == grouptask_id,
            GroupTask.group_id == group_id,
        )
    )
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"participant not found with id: {participant_id} in group_id: {group_id} for grouptask_id: {grouptask_id}"
        )
        raise HTTPException(status_code=404, detail="invalid task id")
    participant.paid = True
    logger.info(
        f"{username} successfully marked assignment with  id '{participant_id}' as complete"
    )
    try:
        await db.commit()
        await db.refresh(participant)
    except IntegrityError:
        await db.rollback()
        logger.error(f"Integrity error by {username}")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        logger.exception(f"internal server error by {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"{username} successfully marked assignment with id '{participant_id}' as complete"
    )
    return {
        "status": "success",
        "message": "completed assignment",
        "data": {
            "id": participant_id,
            "username": participant.username,
            "completed": "Yes",
        },
    }


async def paid_levy(
    group_id,
    group_task_id,
    page,
    limit,
    db,
    payload,
):
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
        .join(Participant.group_tasks)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(
                    GroupAdmin.user_id == user_id,
                    GroupAdmin.group_id == group_id,
                    GroupTask.id == group_task_id,
                ),
                and_(
                    Participant.group_id == group_id,
                    GroupTask.id == group_task_id,
                    Participant.username == username,
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"user_id: {user_id} is not a participant in group_id: {group_id} for grouptask_id: {group_task_id}"
        )
        raise HTTPException(status_code=403, detail="not a participant")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            GroupTask.group_id == group_id,
            GroupTask.id == group_task_id,
            Participant.paid.is_(True),
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"{username} successfully queried paid levies, total: {total}")
    data = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not data:
        logger.warning(
            f"{username} has no paid levies in group_id: {group_id} for grouptask_id: {group_task_id}"
        )
        raise HTTPException(
            status_code=404, detail="no participant has paid their levy"
        )
    logger.info(f"{username} successfully queried paid levies")
    check = PaginatedMetadata[ParticipantResponse](
        items=[ParticipantResponse.model_validate(part) for part in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    logger.info(f"{username} successfully queried paid levies")
    return StandardResponse(
        status="success",
        message="task executed",
        data=check,
    )


async def delete_one(
    group_id,
    task_id,
    participant_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(GroupAdmin).where(
        GroupAdmin.group_id == group_id, GroupAdmin.user_id == user_id
    )
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(
            f"{username}, tried removing a participant without admin powers: {participant_id}"
        )
        raise HTTPException(status_code=403, detail="not admin")
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .where(
            Participant.id == participant_id,
            GroupTask.id == task_id,
            GroupTask.group_id == group_id,
        )
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"participant not found with id: {participant_id} in group_id: {group_id} for grouptask_id: {task_id}"
        )
        raise HTTPException(status_code=404, detail="participant not found")
    logger.info("removed participant %s", participant_id)
    try:
        await db.delete(result)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.error(f"Integrity error by {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    except Exception as e:
        await db.rollback()
        logger.exception(f"internal server error by {username}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"{username} successfully removed participant with id '{participant_id}'"
    )
    return {
        "status": "success",
        "message": "removed participant",
        "data": {
            "id": result.id,
            "username": result.username,
            "removed": "Yes",
        },
    }
