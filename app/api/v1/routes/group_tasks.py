from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.verify_jwt import verify_token
from app.core.db_session import get_db
from app.api.v1.models import (
    TaskResponseG,
    StandardResponse,
    PaginatedMetadata,
    Piggy,
    ContributeResponseG,
    BrokeResponse,
    TaskT,
    TaskRes,
)
from app.services import grouptask_service

router = APIRouter(prefix="/g_tasks", tags=["Group Tasks"])


@router.post("/create")
async def create_task(
    task: TaskRes,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.create_tasks(db=db, payload=payload, task=task)


@router.put(
    "/update_target", response_model=StandardResponse, response_model_exclude_none=True
)
async def update_target(
    task: TaskT,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.update_target(db=db, payload=payload, task=task)


@router.put(
    "/savings", response_model=StandardResponse, response_model_exclude_none=True
)
async def piggy_bank(
    task: Piggy,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.piggy(db=db, payload=payload, task=task)


@router.get(
    "/list",
    response_model=StandardResponse[PaginatedMetadata[TaskResponseG]],
    response_model_exclude_none=True,
)
async def view(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.view_all_tasks(
        db=db, payload=payload, group_id=group_id, page=page, limit=limit
    )


@router.get(
    "/view_one/{group_id}/{task_id}",
    response_model=StandardResponse,
    response_model_exclude_none=True,
)
async def one_task(
    group_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.fetch_some(
        group_id=group_id, task_id=task_id, db=db, payload=payload
    )


@router.post("/records")
async def book_keeping(
    group_id: int,
    grouptask_id: int,
    username: str,
    contribution: float,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.contribute(
        db=db,
        payload=payload,
        group_id=group_id,
        group_task_id=grouptask_id,
        username=username,
        contribution=contribution,
    )


@router.get(
    "/get_records",
    response_model=StandardResponse[PaginatedMetadata[ContributeResponseG]],
    response_model_exclude_none=True,
)
async def contribution_records(
    group_id: int,
    grouptask_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.get_contribution(
        db=db,
        payload=payload,
        group_id=group_id,
        grouptask_id=grouptask_id,
        page=page,
        limit=limit,
    )


@router.put("/mark", response_model=StandardResponse)
async def mark_complete(
    group_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.mark_target(
        db=db, payload=payload, group_id=group_id, task_id=task_id
    )


@router.get(
    "/completed",
    response_model=StandardResponse[PaginatedMetadata[TaskResponseG]],
    response_model_exclude_none=True,
)
async def completed_target(
    group_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.completed_target(
        db=db,
        payload=payload,
        group_id=group_id,
        page=page,
        limit=limit,
    )


@router.post("/broke_check")
async def broke_shield(
    plan: BrokeResponse,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.broke_shield(db=db, payload=payload, plan=plan)


@router.post("/feasibility_check")
async def feasible(
    feasibility: BrokeResponse,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.feasible(
        db=db, payload=payload, feasibility=feasibility
    )


@router.delete("/delete", response_model=StandardResponse)
async def delete_one(
    group_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await grouptask_service.delete_one(
        db=db, payload=payload, group_id=group_id, task_id=task_id
    )
