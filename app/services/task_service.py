from app.models_sql import Task, Contribute, User
from sqlalchemy import func, select, delete, func
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, date
from fastapi import HTTPException
from app.api.v1.models import (
    TaskResponse,
    PaginatedResponse,
    StandardResponse,
    PaginatedMetadata,
    ContributeResponse,
)
from app.log.logger import get_loggers


logger = get_loggers("tasks")


async def create_tasks(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="Username mismatch. Unauthorized task creation."
        )
    target = (
        await db.execute(
            select(Task)
            .join(User)
            .where(
                User.id == user_id,
                Task.target == task.target,
                Task.complete == False,
                Task.day_of_target >= datetime.now(timezone.utc),
            )
        )
    ).scalar_one_or_none()
    if target:
        raise HTTPException(
            status_code=403,
            detail="complete the initiated target, before starting a new one",
        )
    new_task = Task(
        user_id=user_id,
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
        logger.info(f"task successfully created by {username}. task: {task.target}")
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return {"task saved": new_task.target}


async def piggy(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="Username mismatch. Unauthorized task creation."
        )
    stmt = select(Task).where(Task.id == task.task_id)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="No target found for this user")
    if result.amount_saved is None:
        result.amount_saved = 0.0
    result.amount_saved += task.amount_saved_for_the_day
    try:
        await db.commit()
        await db.refresh(result)
        required = result.amount_required_to_hit_target - result.amount_saved
        data = TaskResponse.model_validate(result)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return StandardResponse(
        status=f"you have added {task.amount_saved_for_the_day} towards your target amount of {result.amount_required_to_hit_target}",
        message=f" total amount needed to hit your target: {required}",
        data=data,
    )


async def contribute(
    target,
    contribution,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="Username mismatch. Unauthorized task creation."
        )
    stmt = select(Task).where(Task.target == target)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=404, detail="no such target")
    contri = Contribute(
        target=target,
        contribution=contribution,
        time=datetime.now(timezone.utc),
        user_id=user_id,
    )
    try:
        db.add(contri)
        await db.commit()
        await db.refresh(contri)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return "saved"


async def get_contribution(
    target,
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="Username mismatch. Unauthorized task creation."
        )
    offset = (page - 1) * limit
    stmt = select(Contribute).where(
        Contribute.user_id == user_id, Contribute.target == target
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    contribution = select(
        func.sum(Contribute.contribution).over(order_by=Contribute.id).label("total")
    ).where(Contribute.user_id == user_id, Contribute.target == target)
    contribution_total = (await db.execute(contribution)).scalars().all()
    result = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not result:
        raise HTTPException(status_code=404, detail="no contribution found")
    items = []
    for contribute in result:
        collection = ContributeResponse.model_validate(contribute)
        collection.total = contribution_total
        items.append(collection)
    data = PaginatedMetadata[ContributeResponse](
        items=items,
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    return StandardResponse(status="success", message="contributions", data=data)


async def broke_shield(
    plan,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")

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
    feas,
    payload,
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="forbidden entry")
    today = date.today()
    days = (feas.day_of_target - today).days
    daily_savings = feas.amount_required / days
    daily_income = feas.monthly_income / 30
    if days <= 0:
        raise HTTPException(status_code=400, detail="End date must be in the future")
    if days <= 30:
        if daily_savings > daily_income * 0.7:
            return "not feasible"
        if daily_savings > daily_income * 0.5:
            return "capital intensive"
        if daily_savings > daily_income * 0.3:
            return "feasible with persistence"
        else:
            return "feasible"
    if days > 30:
        month_remaining = days / 30
        income = feas.monthly_income * month_remaining
        if feas.amount_required > income * 0.5:
            return "not feasible"
        if feas.amount_required > income * 0.3:
            return "capital intensive"
        if feas.amount_required > income * 0.2:
            return "feasible with persistence"
        else:
            return "feasible"


async def update_task(
    task,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=403, detail="Username mismatch. Unauthorized task creation."
        )
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task.task_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(f"{username}, tried updating a nonexistent task")
        raise HTTPException(status_code=404, detail="task not found")
    if task.new_day_of_target is not None:
        data.day_of_target = task.new_day_of_target
    if task.new_target is not None:
        data.target = task.new_target
    if task.new_amount_required is not None:
        data.amount_required_to_hit_target = task.new_amount_required
    if task.new_monthly_income is not None:
        data.monthly_income = task.new_monthly_income
    try:
        data.complete = False
        await db.commit()
        await db.refresh(data)
        logger.info(f"task successfully updated from by {username}")
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return StandardResponse(
        status="success",
        message="Task updated successfully",
        data={
            "new deadline": task.new_day_of_target,
            "new_target": task.new_target,
            "new_target_amount": task.new_amount_required,
            "time of update": datetime.now(timezone.utc),
        },
    )


async def view_all_tasks(
    db,
    page,
    limit,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    logger.info(
        f"Fetching tasks for user_id={user_id}, username={username}, page={page}, limit={limit}"
    )
    offset = (page - 1) * limit
    stmt = select(Task).where(Task.user_id == user_id)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    tasks = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not tasks:
        logger.warning(f"all tasks queried, but none found for {username}")
        raise HTTPException(status_code=404, detail="No target found")
    data = PaginatedMetadata[TaskResponse](
        items=[TaskResponse.model_validate(task) for task in tasks],
        pagination=PaginatedResponse(page=page, limit=limit, total=total),
    )
    logger.info(
        f"all tasks fetched successfully by {username}, page={page}, limit={limit}, total={total}"
    )
    return StandardResponse(status="success", message="tasks data", data=data)


async def fetch_some(
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        logger.warning(f"{username} unsuccessfully queried task with id {task_id}")
        raise HTTPException(status_code=404, detail="No target found")
    data = TaskResponse.model_validate(result)

    logger.info(f"{username}, fetched for task with id {task_id}")
    return StandardResponse(status="success", message="requested data", data=data)


async def completed(
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
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


async def completed_data(
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    stmt = select(Task).where(Task.user_id == user_id, Task.complete.is_(True))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    data = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not data:
        raise HTTPException(status_code=404, detail="you have no completed target")
    logger.info(f"{username} successfully queried completed tasks")
    check = PaginatedMetadata[TaskResponse](
        items=[TaskResponse.model_validate(task) for task in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    return StandardResponse(
        status="success",
        message="task executed",
        data=check,
    )


async def not_complete(
    page,
    limit,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    stmt = select(Task).where(Task.user_id == user_id, Task.complete == False)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    data = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    if not data:
        raise HTTPException(status_code=404, detail="you have no uncompleted target")
    logger.info(f"{username} successfully queried uncompleted tasks")
    check = PaginatedMetadata[TaskResponse](
        items=[TaskResponse.model_validate(task) for task in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    return StandardResponse(
        status="success",
        message="task executed",
        data=check,
    )


async def unaccomplished(
    db,
    page,
    limit,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    offset = (page - 1) * limit
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(
        Task.user_id == user_id,
        Task.day_of_target <= now,
        Task.complete.is_(False),
    )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar()
    data = (
        (
            await db.execute(
                stmt.order_by(Task.day_of_target.asc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not data:
        raise HTTPException(status_code=404, detail="you have no unaccomplished task")
    logger.info(f"{username} successfully queried expired tasks")
    check = PaginatedMetadata[TaskResponse](
        items=[TaskResponse.model_validate(task) for task in data],
        pagination=PaginatedResponse(
            page=page,
            limit=limit,
            total=total,
        ),
    )
    return StandardResponse(status="success", message="task executed", data=check)


async def delete_all(db, payload):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = delete(Task).where(Task.user_id == user_id)
    data = await db.execute(stmt)
    if data.rowcount == 0:
        logger.warning(f"{username}, tried deleting a blank database")
        return {"no data to clear"}
    try:
        await db.commit()
        logger.info(f"{username} successfully wiped their database")
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return {"message": "data wiped"}


async def delete_one(
    task_id,
    db,
    payload,
):
    user_id = payload.get("user_id")
    username = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=403, detail="Unauthorized access.")
    stmt = select(Task).where(Task.user_id == user_id, Task.id == task_id)
    data = (await db.execute(stmt)).scalar_one_or_none()
    if not data:
        logger.warning(
            f"{username}, tried deleting a nonexistent task, task id: {task_id}"
        )
        raise HTTPException(status_code=404, detail="invalid field")
    try:
        await db.delete(data)
        await db.commit()
        logger.info("deleted tasks %s", task_id)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="internal server error")
    return {
        "status": "success",
        "message": "deleted target",
        "data": {
            "id": data.id,
            "username": username,
            "description": data.target,
            "deleted": "Yes",
        },
    }
