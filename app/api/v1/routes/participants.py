from app.models_sql import Participant, GroupAdmin, GroupTask, Member
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db_session import get_db
from sqlalchemy import func, select, or_, and_
from fastapi import APIRouter
from fastapi import HTTPException, Depends, Query
from app.auth.verify_jwt import verify_token
from app.api.v1.models import (
    Participants,
    PaginatedResponse,
    StandardResponse,
    PaginatedMetadata,
    ParticipantResponse,
)
from sqlalchemy.exc import IntegrityError
from app.services import participant_service

router = APIRouter(prefix="/member", tags=["Participants"])


@router.post("/participants")
async def add_participant(
    participate: Participants,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.dev(
        db=db, payload=payload, participate=participate
    )


@router.get(
    "/reveal_all_participants",
    response_model=StandardResponse[PaginatedMetadata[ParticipantResponse]],
    response_model_exclude_none=True,
)
async def view_participants(
    group_id: int,
    grouptask_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    payload: dict = Depends(verify_token),
):
    return await participant_service.get_all(
        group_id=group_id,
        grouptask_id=grouptask_id,
        db=db,
        page=page,
        limit=limit,
        payload=payload,
    )


@router.put("/mark_assignment", response_model=StandardResponse)
async def mark_assignment_complete(
    group_id: int,
    grouptask_id: int,
    participant_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.mark_assignment_complete(
        group_id=group_id,
        grouptask_id=grouptask_id,
        participant_id=participant_id,
        db=db,
        payload=payload,
    )


@router.get(
    "/completed_assignment",
    response_model=StandardResponse[PaginatedMetadata[ParticipantResponse]],
    response_model_exclude_none=True,
)
async def completed_assignments(
    group_id: int,
    grouptask_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.completed_assignments(
        group_id=group_id,
        group_task_id=grouptask_id,
        page=page,
        limit=limit,
        db=db,
        payload=payload,
    )


@router.put("/mark_payment", response_model=StandardResponse)
async def mark_levy(
    group_id: int,
    grouptask_id: int,
    participant_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.mark_levy(
        group_id=group_id,
        grouptask_id=grouptask_id,
        participant_id=participant_id,
        db=db,
        payload=payload,
    )


@router.get(
    "/completed_payment",
    response_model=StandardResponse[PaginatedMetadata[ParticipantResponse]],
    response_model_exclude_none=True,
)
async def paid_levy(
    group_id: int,
    grouptask_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.paid_levy(
        group_id=group_id,
        group_task_id=grouptask_id,
        page=page,
        limit=limit,
        db=db,
        payload=payload,
    )


@router.delete("/delete", response_model=StandardResponse)
async def delete_one(
    group_id: int,
    task_id: int,
    participant_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await participant_service.delete_one(
        group_id=group_id,
        task_id=task_id,
        participant_id=participant_id,
        db=db,
        payload=payload,
    )
