from app.log.logger import get_loggers
from typing import List
from fastapi import Request
from app.api.v1.models import CommentResponse, Blogger, ReactionsSummary
import orjson

logger = get_loggers("helpers")


def _supabase(request: Request):
    return request.app.state.supabase


async def generate_signed_urls(
    request: Request,
    filenames: list[str],
    bucket: str = "codeemmanuel",
    context: str = "files",
):
    if filenames is None or len(filenames) == 0:
        return None
    try:
        client = _supabase(request)
        logger.debug("BASE URL:", client.storage._client.base_url)
        url_response = await client.storage.from_(bucket).create_signed_urls(
            filenames, 7200
        )
        data = url_response["data"] if isinstance(url_response, dict) else url_response
        result = {}
        for entry in data:
            signed = entry["signedURL"] if "signedURL" in entry else entry["signedUrl"]
            result[entry["path"]] = signed
        return result
    except Exception as e:
        logger.exception("failed generating signed urls for %s, %s", context, e)
        return None


async def generate_signed_url(
    request: Request,
    filename: str,
    bucket: str = "codeemmanuel",
    context: str = "files",
):
    if not filename:
        return None
    try:
        client = _supabase(request)
        url_response = await client.storage.from_(bucket).create_signed_url(
            filename, 7200
        )
        return (
            url_response["signedURL"]
            if url_response["signedURL"]
            else url_response["signedUrl"]
        )
    except Exception:
        logger.exception("failed generating signed url for %s", context)
        return None


def build_comment_response(result, pic: dict | None, react: dict | None):
    if not result:
        return None
    comment_data = CommentResponse.model_validate(result)
    pics = result.user.profile_picture if result.user.profile_picture else None
    comment_data.profile_picture = pic.get(pics) if pic and pics else None
    comment_data.name = result.user.name
    comment_data.reactions = (
        react.get(result.id)
        if react and comment_data.reacts_count > 0
        else ReactionsSummary()
    ) or ReactionsSummary()
    return comment_data


def build_blog_response(
    result,
    profile_pic: dict | None,
    image_map: dict | None,
    react: dict | None,
):
    blog_data = Blogger.model_validate(result) if result else None
    if blog_data:
        filename = result.user.profile_picture if result.user.profile_picture else None
        blog_data.profile_picture = (
            profile_pic.get(filename) if profile_pic and filename else None
        )
        blog_data.name = result.user.name
        filename = orjson.loads(result.image) if result.image else None
        if isinstance(filename, list):
            blog_data.image = (
                [
                    url
                    for f in filename
                    if image_map and (url := image_map.get(f)) is not None
                ]
                if filename
                else None
            )
        else:
            blog_data.image = (
                image_map.get(filename) if image_map and filename else None
            )
        blog_data.reactions = (
            react.get(result.id)
            if react and blog_data.reacts_count > 0
            else ReactionsSummary()
        ) or ReactionsSummary()
    return blog_data
