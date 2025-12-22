from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter
from app.core.db_session import get_db
from fastapi import Depends, Query
from app.auth.verify_jwt import verify_token
from app.api.v1.models import (
    TaskResponse,
    StandardResponse,
    PaginatedMetadata,
    TaskT,
    ContributeResponse,
    Piggy,
    BrokeResponse,
    TaskRes,
)
from app.services import task_service

router = APIRouter(prefix="/plot", tags=["Target"])


@router.post("/create")
async def create_tasks(
    task: TaskRes,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.create_tasks(task=task, db=db, payload=payload)


@router.put(
    "/savings", response_model=StandardResponse, response_model_exclude_none=True
)
async def piggy_bank(
    task: Piggy,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.piggy(task=task, db=db, payload=payload)


@router.post("/record")
async def contribute(
    target: str,
    contribution: float,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.contribute(
        target=target, contribution=contribution, db=db, payload=payload
    )


@router.post(
    "/get_records",
    response_model=StandardResponse[PaginatedMetadata[ContributeResponse]],
    response_model_exclude_none=True,
)
async def contribution_record(
    target: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.get_contribution(
        target=target, db=db, payload=payload, page=page, limit=limit
    )


@router.post("/plan")
async def broke_shield(
    plan: BrokeResponse,
    payload: dict = Depends(verify_token),
):
    return await task_service.broke_shield(plan=plan, payload=payload)


@router.post("/feasibility_check")
async def feasible(
    feasibility: BrokeResponse,
    payload: dict = Depends(verify_token),
):
    return await task_service.feasible(feas=feasibility, payload=payload)


@router.put("/update", response_model=StandardResponse)
async def update_task(
    task: TaskT,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.update_task(task=task, db=db, payload=payload)


@router.get(
    "/list",
    response_model=StandardResponse[PaginatedMetadata[TaskResponse]],
    response_model_exclude_none=True,
)
async def view_tasks(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    payload: dict = Depends(verify_token),
):
    return await task_service.view_all_tasks(
        db=db, payload=payload, page=page, limit=limit
    )


@router.get(
    "/view_one/{task_id}",
    response_model=StandardResponse[TaskResponse],
    response_model_exclude_none=True,
)
async def view_a_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.fetch_some(task_id=task_id, db=db, payload=payload)


@router.put("/mark_task/{task_id}", response_model=StandardResponse)
async def mark_complete(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.completed(task_id=task_id, db=db, payload=payload)


@router.get(
    "/completed_tasks",
    response_model=StandardResponse[PaginatedMetadata[TaskResponse]],
    response_model_exclude_none=True,
)
async def completed(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.completed_data(
        db=db, payload=payload, page=page, limit=limit
    )


@router.get(
    "/undone",
    response_model=StandardResponse[PaginatedMetadata[TaskResponse]],
    response_model_exclude_none=True,
)
async def not_complete(
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.not_complete(
        db=db, payload=payload, page=page, limit=limit
    )


@router.get(
    "/unaccomplished_tasks",
    response_model=StandardResponse[PaginatedMetadata[TaskResponse]],
    response_model_exclude_none=True,
)
async def unaccomplished(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    payload: dict = Depends(verify_token),
):
    return await task_service.unaccomplished(
        db=db, payload=payload, page=page, limit=limit
    )


@router.delete("/clear_all")
async def delete_all(
    db: AsyncSession = Depends(get_db), payload: dict = Depends(verify_token)
):
    return await task_service.delete_all(db=db, payload=payload)


@router.delete("/delete/{task_id}", response_model=StandardResponse)
async def delete_one(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await task_service.delete_one(task_id=task_id, db=db, payload=payload)
