from fastapi import APIRouter, Depends, Query, HTTPException
from app.api.v1.models import (
    OpinionResponse,
    StandardResponse,
    OpinionRes,
    PaginatedMetadata,
    PaginatedResponse,
    Voting,
)
from app.models_sql import (
    Opinion,
    GroupTask,
    Participant,
    Group,
    OpinionVote,
    OpinionEnum,
)
from app.auth.verify_jwt import verify_token
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func
from app.core.db_session import get_db
from app.services import opinions_service

router = APIRouter(prefix="/suggest", tags=["Opinion"])


@router.post("/opinion")
async def create_opinion(
    op: OpinionRes,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await opinions_service.create_opinion(op=op, db=db, payload=payload)


@router.get(
    "/view_opinion",
    response_model=StandardResponse[PaginatedMetadata[OpinionResponse]],
    response_model_exclude_none=True,
)
async def view_opinions(
    group_id: int,
    task_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await opinions_service.fetch(
        group_id=group_id,
        task_id=task_id,
        page=page,
        limit=limit,
        db=db,
        payload=payload,
    )


@router.post("vote")
async def votes(
    group_id: int,
    task_id: int,
    opinion_id: int,
    vote: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await opinions_service.votes(
        group_id=group_id,
        task_id=task_id,
        opinion_id=opinion_id,
        vote=vote,
        db=db,
        payload=payload,
    )


@router.delete("/delete", response_model=StandardResponse)
async def delete_one(
    opinion_id: int,
    group_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await opinions_service.delete_one(
        opinion_id=opinion_id,
        group_id=group_id,
        task_id=task_id,
        db=db,
        payload=payload,
    )
