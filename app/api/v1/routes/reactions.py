from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends
from app.core.db_session import get_db
from app.auth.verify_jwt import verify_token
from app.services import reaction_service

router = APIRouter(prefix="/react", tags=["Reactions"])


@router.post("/react")
async def react_type(
    reaction_type: str,
    comment_id: int | None = None,
    blog_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(verify_token),
):
    return await reaction_service.react_type(
        reaction_type=reaction_type,
        comment_id=comment_id,
        blog_id=blog_id,
        db=db,
        payload=payload,
    )
