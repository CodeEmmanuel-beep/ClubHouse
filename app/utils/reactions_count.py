from app.models_sql import React
from app.api.v1.models import ReactionsSummary
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models_sql import OpinionVote
from app.api.v1.models import Voting


async def react_summary(
    db: AsyncSession, comment_id: list[int]
) -> dict[int, ReactionsSummary]:
    if isinstance(comment_id, int):
        comment_id = [comment_id]
    counts = (
        await db.execute(
            select(React.comment_id, React.type, func.count(React.id))
            .where(React.comment_id.in_(comment_id))
            .group_by(React.comment_id, React.type)
            .order_by(React.type)
        )
    ).all()
    summary_map: dict[int, dict[str, int]] = {}
    for comment_id_row, rtype, count in counts:
        key = rtype.name if hasattr(rtype, "name") else rtype
        summary_map.setdefault(comment_id_row, {})[key] = count
    result: dict[int, ReactionsSummary] = {}
    for cid in comment_id:
        summary = summary_map.get(cid, {})
        result[cid] = ReactionsSummary(
            like=summary.get("like", 0),
            love=summary.get("love", 0),
            laugh=summary.get("laugh", 0),
            angry=summary.get("angry", 0),
            wow=summary.get("wow", 0),
            sad=summary.get("sad", 0),
        )
    return result


async def blog_react_summary(
    db: AsyncSession, blog_id: list[int]
) -> dict[int, ReactionsSummary]:
    if isinstance(blog_id, int):
        blog_id = [blog_id]
    react_count = (
        await db.execute(
            select(React.blog_id, React.type, func.count(React.id))
            .where(React.blog_id.in_(blog_id))
            .group_by(React.blog_id, React.type)
            .order_by(React.type)
        )
    ).all()
    summary_map: dict[int, dict[str, int]] = {}
    for blog, rtype, count in react_count:
        key = rtype.name if hasattr(rtype, "name") else rtype
        summary_map.setdefault(blog, {})[key] = count
    result: dict[int, ReactionsSummary] = {}
    for bld in blog_id:
        summary = summary_map.get(bld, {})
        result[bld] = ReactionsSummary(
            like=summary.get("like", 0),
            love=summary.get("love", 0),
            wow=summary.get("wow", 0),
            laugh=summary.get("laugh", 0),
            sad=summary.get("sad", 0),
            angry=summary.get("angry", 0),
        )
    return result


async def vote_type(
    db: AsyncSession, group_id, task_id, opinion_id: list[int]
) -> dict[int, Voting]:
    stmt = (
        select(OpinionVote.opinion_id, OpinionVote.vote, func.count(OpinionVote.id))
        .where(
            OpinionVote.opinion_id.in_(opinion_id),
            OpinionVote.group_id == group_id,
            OpinionVote.grouptask_id == task_id,
        )
        .group_by(OpinionVote.opinion_id, OpinionVote.vote)
    )
    counts = (await db.execute(stmt)).all()
    summary_map: dict[int, dict[str, int]] = {}
    for opinion, rtype, count in counts:
        key = rtype.name if hasattr(rtype, "name") else rtype
        summary_map.setdefault(opinion, {})[key] = count
    result: dict[int, Voting] = {}
    for op in opinion_id:
        summary = summary_map.get(op, {})
        result[op] = Voting(
            upvote=summary.get("upvote", 0), downvote=summary.get("downvote", 0)
        )
    return result
