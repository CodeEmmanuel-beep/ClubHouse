from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from app.models_sql import (
    GroupAdmin,
    Member,
    GroupTask,
    Contribute,
    Participant,
)
from app.api.v1.models import (
    TaskResponseG,
    StandardResponse,
    PaginatedMetadata,
    PaginatedResponse,
    ContributeResponseG,
)
from app.log.logger import get_loggers
from datetime import timezone, datetime, date

logger = get_loggers("g_tasks")


async def create_tasks(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(
            status_code=401, detail="Username mismatch. Unauthorized task creation."
        )
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == task.group_id
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {task.group_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    new_task = GroupTask(
        user_id=user_id,
        group_id=task.group_id,
        target=task.target,
        amount_required_to_hit_target=task.amount_required_to_hit_target,
        day_of_target=task.day_of_target,
        monthly_income=task.monthly_income,
        amount_saved=task.amount_saved,
        time_of_initial_prep=datetime.now(timezone.utc),
    )
    try:
        db.add(new_task)
        await db.commit()
        await db.refresh(new_task)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Group task creation failed by user_id: {user_id} for group_id: {task.group_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"task successfully created by {user_id}")
    return {"task saved": new_task.target}


async def update_target(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="Unauthorized target update.")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == task.group_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt to update target by user_id: {user_id} to group_id: {task.group_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    stmt = (
        select(GroupTask)
        .options(selectinload(GroupTask.opinions), selectinload(GroupTask.participants))
        .where(GroupTask.id == task.task_id, GroupTask.group_id == task.group_id)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"task not found for task_id: {task.task_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=404, detail="No target found")
    if task.new_target is not None:
        result.target = task.new_target
    if task.new_amount_required is not None:
        result.amount_required_to_hit_target = task.new_amount_required
    if task.new_day_of_target is not None:
        result.day_of_target = task.new_day_of_target
    if task.new_monthly_income is not None:
        result.monthly_income = task.new_monthly_income
    try:
        result.complete = False
        result.edited = True
        await db.commit()
        await db.refresh(result)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Failed to update target for task_id: {task.task_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    data = TaskResponseG.model_validate(result)
    logger.info(
        f"task updated successfully for task_id: {task.task_id} by user_id: {user_id}"
    )
    return StandardResponse(status="success", message="task updated", data=data)


async def piggy(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(
            status_code=401, detail="Username mismatch. Unauthorized task creation."
        )
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == task.group_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {task.group_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    stmt = (
        select(GroupTask)
        .where(GroupTask.id == task.task_id)
        .options(
            selectinload(GroupTask.opinions),
            selectinload(GroupTask.participants),
        )
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(
            f"task not found for task_id: {task.task_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=404, detail="No target found")
    result.amount_saved += task.amount_saved_for_the_day
    try:
        await db.commit()
        await db.refresh(result)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Failed to update savings for task_id: {task.task_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    required = result.amount_required_to_hit_target - result.amount_saved
    data = TaskResponseG.model_validate(result)
    logger.info(
        f"savings updated successfully for task_id: {task.task_id} by user_id: {user_id}"
    )
    return StandardResponse(
        status=f"you have added {task.amount_saved_for_the_day} towards your target amount of {result.amount_required_to_hit_target}",
        message=f" total amount needed to hit your target: {required}",
        data=data,
    )


async def view_all_tasks(
    group_id,
    db,
    page,
    limit,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    logger.info(
        f"Fetching tasks for user_id={user_id}, username={username}, page={page}, limit={limit}"
    )
    stmt = (
        select(GroupTask)
        .join(GroupTask.participants, isouter=True)
        .where(
            or_(
                and_(GroupTask.user_id == user_id, GroupTask.group_id == group_id),
                and_(Participant.username == username, GroupTask.group_id == group_id),
            )
        )
    ).limit(1)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="you are not a member of any task")
    stmt = (
        select(GroupTask)
        .join(GroupTask.participants, isouter=True)
        .options(
            selectinload(GroupTask.opinions),
            selectinload(GroupTask.participants),
        )
        .where(
            (
                or_(
                    and_(GroupTask.user_id == user_id, GroupTask.group_id == group_id),
                    and_(
                        Participant.username == username, GroupTask.group_id == group_id
                    ),
                )
            )
        )
    ).distinct()
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    logger.info(
        f"user_id: {user_id} accessed total tasks for group_id: {group_id}, total tasks: {total}"
    )
    tasks = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not tasks:
        logger.warning(f"all tasks queried, but none found for {username}")
        raise HTTPException(status_code=404, detail="No target found")
    data = PaginatedMetadata[TaskResponseG](
        items=[TaskResponseG.model_validate(task) for task in tasks],
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(
        f"all tasks fetched successfully by {username}, page={page}, limit={limit}, total={total}"
    )
    return StandardResponse(status="success", message="tasks data", data=data)


async def fetch_some(
    group_id,
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = stmt = (
        select(GroupAdmin)
        .join(Participant, Participant.group_id == GroupAdmin.group_id)
        .join(GroupTask, GroupTask.group_id == GroupAdmin.group_id)
        .where(
            (
                or_(
                    and_(
                        GroupAdmin.user_id == user_id,
                        GroupTask.group_id == group_id,
                    ),
                    and_(
                        Participant.username == username,
                        GroupTask.group_id == group_id,
                    ),
                )
            )
        )
    ).limit(1)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"{username} tried to access an authorized task {task_id}")
        raise HTTPException(status_code=404, detail="No target found")
    stmt = (
        select(GroupTask)
        .options(
            selectinload(GroupTask.opinions),
            selectinload(GroupTask.participants),
        )
        .where(GroupTask.group_id == group_id, GroupTask.id == task_id)
    )
    find = (await db.execute(stmt)).scalar_one_or_none()
    if not find:
        logger.warning(f"{username} unsuccessfully queried task with id {task_id}")
        raise HTTPException(status_code=404, detail="No target found")
    data = TaskResponseG.model_validate(find)
    logger.info(f"{username}, fetched for task with id {task_id}")
    return StandardResponse(status="success", message="requested data", data=data)


async def contribute(
    group_id,
    group_task_id,
    username,
    contribution,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(
            status_code=401, detail="Username mismatch. Unauthorized target creation."
        )
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id
    )
    admin = (await db.execute(stmt)).scalar_one_or_none()
    if not admin:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="not authorized")
    stmt = select(Participant).where(
        Participant.username == username, Participant.group_id == group_id
    )
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="not a participant")
    stmt = select(GroupTask).where(GroupTask.id == group_task_id)
    group_task = (await db.execute(stmt)).scalar_one_or_none()
    if not group_task:
        logger.warning(
            f"group task not found for group_task_id: {group_task_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=404, detail="group task not found")
    contri = Contribute(
        name=username,
        contribution=contribution,
        time=datetime.now(timezone.utc),
        user_id=user_id,
        group_id=group_id,
        grouptask_id=group_task_id,
    )
    try:
        db.add(contri)
        await db.commit()
        await db.refresh(contri)
    except IntegrityError:
        await db.rollback()
        logger.error(
            f"Contribution record creation failed by user_id: {user_id} for group_task_id: {group_task_id}"
        )
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"contribution record successfully created by {user_id} for group_task_id: {group_task_id}"
    )
    return "saved"


async def get_contribution(
    group_id: int,
    grouptask_id: int,
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(
            status_code=401, detail="Username mismatch. Unauthorized task creation."
        )
    offset = (page - 1) * limit
    stmt = (
        select(Participant)
        .join(Participant.group_tasks)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(Participant.group_id == group_id, GroupTask.id == grouptask_id),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(status_code=403, detail="not a participant of this target")
    stmt = select(GroupTask).where(
        GroupTask.id == grouptask_id,
    )
    grouptask = (await db.execute(stmt)).scalars().all()
    if not grouptask:
        logger.warning(
            f"group task not found for grouptask_id: {grouptask_id} by user_id: {user_id}"
        )
        raise HTTPException(status_code=404, detail="target not found")
    p_total = (
        select(Contribute.name, func.sum(Contribute.contribution).label("total"))
        .where(
            Contribute.group_id == group_id,
            Contribute.grouptask_id == grouptask_id,
            Contribute.grouptask_id.isnot(None),
        )
        .group_by(Contribute.name)
    )
    participant_total = (await db.execute(p_total)).all()
    logger.info(
        f"Participant totals calculated for grouptask_id: {grouptask_id} by user_id: {user_id} totals: {participant_total}"
    )
    participant_totals = [
        {"name": row.name, "total": row.total} for row in participant_total
    ]
    group_total = select(func.sum(Contribute.contribution).label("group_total")).where(
        Contribute.group_id == group_id, Contribute.grouptask_id == grouptask_id
    )
    g_total = (await db.execute(group_total)).scalar() or 0
    logger.info(
        f"Group total calculated for grouptask_id: {grouptask_id} by user_id: {user_id} total: {g_total}"
    )
    stmt = select(Contribute).where(
        Contribute.group_id == group_id,
        Contribute.user_id == user_id,
        Contribute.grouptask_id == grouptask_id,
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    logger.info(
        f"Total contributions retrieved for grouptask_id: {grouptask_id} by user_id: {user_id} total: {total}"
    )
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    items = []
    for con in result:
        collection = ContributeResponseG.model_validate(con)
        collection.member_total = participant_totals
        collection.group_total = g_total
        items.append(collection)
    data = PaginatedMetadata[ContributeResponseG](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info("Paginated data prepared successfully for '%s'", user_id)
    return StandardResponse(status="success", message="contributions", data=data)


async def mark_target(
    group_id,
    task_id,
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
            f"{username}, tried marking a task as complete, id attempted, {task_id}"
        )
        raise HTTPException(status_code=404, detail="not authorized")
    stmt = select(GroupTask).where(
        GroupTask.group_id == group_id, GroupTask.id == task_id
    )
    tasks = (await db.execute(stmt)).scalar_one_or_none()
    if not tasks:
        logger.warning(
            f"{username}, tried marking an invalid id as complete, id attempted, {task_id}"
        )
        raise HTTPException(status_code=404, detail="invalid task id")
    target = datetime.combine(
        tasks.day_of_target, datetime.min.time(), tzinfo=timezone.utc
    )
    if target < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="This task is expired",
        )
    if tasks.amount_saved < tasks.amount_required_to_hit_target:
        raise HTTPException(
            status_code=400,
            detail="you have not saved up to the amount required for this task",
        )
    tasks.complete = True
    logger.info(
        f"{username} successfully marked task with task id '{task_id}' as complete"
    )
    try:
        await db.commit()
        await db.refresh(tasks)
    except IntegrityError:
        logger.info(f"Integrity error by {username}")
        await db.rollback()
        return StandardResponse(
            status="failure", message="Duplicate entry or constraint violation"
        )
    logger.info(
        f"task with id {task_id} and group_id {group_id} marked complete successfully by {username}"
    )
    return {
        "status": "success",
        "message": "completed task",
        "data": {
            "id": tasks.id,
            "username": username,
            "description": tasks.target,
            "completed": "Yes",
        },
    }


async def completed_target(
    group_id,
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
    stmt = (
        select(Participant)
        .join(GroupAdmin, GroupAdmin.group_id == Participant.group_id)
        .where(
            or_(
                and_(GroupAdmin.user_id == user_id, GroupAdmin.group_id == group_id),
                and_(
                    Participant.group_id == group_id, Participant.username == username
                ),
            )
        )
    ).limit(1)
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if not participant:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {group_id}"
        )
        raise HTTPException(
            status_code=403, detail="not a participant of this group target"
        )
    stmt = (
        select(GroupTask)
        .options(selectinload(GroupTask.opinions), selectinload(GroupTask.participants))
        .where(
            GroupTask.group_id == group_id,
            GroupTask.complete.is_(True),
        )
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0
    logger.info(f"{username} retrieved total count of completed tasks total: {total}")
    data = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not data:
        logger.warning(f"{username} queried completed tasks but found none")
        raise HTTPException(status_code=404, detail="you have no completed target")
    logger.info(f"{username} successfully queried completed tasks")
    check = PaginatedMetadata[TaskResponseG](
        items=[TaskResponseG.model_validate(task) for task in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    logger.info(f"{username} successfully queried completed tasks")
    return StandardResponse(
        status="success",
        message="task executed",
        data=check,
    )


async def broke_shield(
    plan,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Member).where(Member.user_id == user_id)
    result = (await db.execute(stmt)).scalars().all()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {plan.group_id}"
        )
        raise HTTPException(
            status_code=403, detail="must be a member of the group to contribute"
        )
    today = date.today()
    days_remaining = (plan.day_of_target - today).days
    if days_remaining <= 0:
        raise HTTPException(status_code=400, detail="End date must be in the future")

    if days_remaining <= 30:
        feasible_budget = plan.monthly_income / 30
        target = plan.amount_required / days_remaining
        save = (plan.monthly_income - plan.amount_required) / 30
        if feasible_budget < target:
            logger.info(f"Spend plan infeasible for user '{username}'")
            return {"message": "Not feasible: required savings exceeds daily income"}
        if save < target:
            return {"message": "Not feasible: daily savings exceeds daily budget"}
        logger.info(f"Spend plan created for user '{username}'")
        return {
            "feasible daily budget": f"{save:.2f}",
            "daily savings": f"{target:.2f}",
            "days_remaining": days_remaining,
        }

    else:
        month_remaining = days_remaining / 30
        income = month_remaining * plan.monthly_income
        target = plan.amount_required / days_remaining
        budget = income / days_remaining
        saved = income - plan.amount_required
        if budget < target:
            logger.info(f"Spend plan infeasible for user '{username}'")
            return {"message": "Not feasible: required savings exceeds daily budget"}
        if saved < plan.amount_required:
            return {"message": "Not feasible: daily savings exceeds budget"}
        logger.info(f"Spend plan created for user '{username}'")
        return {
            "daily savings": f"{target:.2f}",
            "balance after savings": f"{saved:.2f} ",
            "days_remaining": days_remaining,
        }


async def feasible(
    feasibility,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=401, detail="forbidden entry")
    stmt = select(Member).where(Member.user_id == user_id)
    result = (await db.execute(stmt)).scalars().all()
    if not result:
        logger.warning(
            f"unauthorized access attempt by user_id: {user_id} to group_id: {feasibility.group_id}"
        )
        raise HTTPException(
            status_code=403, detail="must be a member of the group to contribute"
        )
    today = date.today()
    days = (feasibility.day_of_target - today).days
    daily_savings = feasibility.amount_required / days
    daily_income = feasibility.monthly_income / 30
    if days <= 0:
        logger.warning(f"End date must be in the future for user_id: {user_id}")
        raise HTTPException(status_code=400, detail="End date must be in the future")
    if days <= 30:
        logger.info(
            f"Feasibility check performed for user_id: {user_id} with days: {days}"
        )
        if daily_savings > daily_income * 0.6:
            return "not feasible"
        if daily_savings > daily_income * 0.4:
            return "capital intensive"
        if daily_savings > daily_income * 0.2:
            return "feasible with persistence"
        else:
            return "feasible"
    if days > 30:
        logger.info(
            f"Feasibility check performed for user_id: {user_id} with days: {days}"
        )
        month_remaining = days / 30
        income = feasibility.monthly_income * month_remaining
        if feasibility.amount_required > income * 0.4:
            return "not feasible"
        if feasibility.amount_required > income * 0.2:
            return "capital intensive"
        if feasibility.amount_required > income * 0.1:
            return "feasible with persistence"
        else:
            return "feasible"


async def delete_one(
    group_id,
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        logger.warning(f"not a valid user, user_id: {user_id}")
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(GroupAdmin).where(
        GroupAdmin.user_id == user_id,
        GroupAdmin.group_id == group_id,
    )
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(
            f"{username}, tried deleting a task without admin powers: {task_id}"
        )
        raise HTTPException(status_code=403, detail="not admin")
    stmt = select(GroupTask).where(
        GroupTask.id == task_id, GroupTask.group_id == group_id
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"{username}, tried deleting a none existent task: {task_id}")
        raise HTTPException(status_code=404, detail="invalid field")
    try:
        await db.delete(result)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(
        f"task with id {task_id} and group_id {group_id} deleted successfully by {username}"
    )
    return {
        "status": "success",
        "message": "deleted task",
        "data": {
            "id": result.id,
            "username": username,
            "description": result.target,
            "deleted": "Yes",
        },
    }
