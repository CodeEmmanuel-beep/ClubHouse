from fastapi import HTTPException
from sqlalchemy import select
from app.models_sql import User
from app.auth.auth_jwt import (
    create_access_token,
    verify_password,
    hash_password,
    create_refresh_tokens,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from app.auth.verify_jwt import decode_token
from datetime import timedelta
import uuid
from app.api.v1.models import StandardResponse
from app.log.logger import get_loggers
from app.core.scheduler import send_email_name
from email_validator import validate_email, EmailNotValidError

logger = get_loggers("auth")


async def register(
    profile_picture,
    email,
    username,
    password,
    confirm_password,
    name,
    age,
    nationality,
    db,
    get_supabase,
):
    min_age = 13
    if age < min_age:
        logger.warning(
            f"Registration failed: Age {age} is below minimum required {min_age}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"you must be at least {min_age} years old to register",
        )
    min_username_length = 4
    if len(username) < min_username_length:
        raise HTTPException(
            status_code=400,
            detail=f"username must be at least {min_username_length} characters long",
        )
    max_username_length = 20
    if len(username) > max_username_length:
        raise HTTPException(
            status_code=400,
            detail=f"username must not exceed {max_username_length} characters",
        )
    user_exists = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user_exists:
        logger.warning(f"Registration failed: Username {username} already exists")
        raise HTTPException(status_code=400, detail="user already exists")
    try:
        validate_email(email)
    except EmailNotValidError:
        raise HTTPException(status_code=400, detail="enter a valid email address")
    email_exists = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if email_exists:
        logger.info(f"Registration failed {email} already exists")
        raise HTTPException(
            status_code=400, detail="email already in use by another user"
        )
    if password != confirm_password:
        raise HTTPException(
            status_code=400, detail="confirm password does not match password"
        )
    filename = None
    if profile_picture is not None:
        try:
            filename = f"{uuid.uuid4()}_{secure_filename(profile_picture.filename)}"
            file_bytes = await profile_picture.read()
            res = await get_supabase.storage.from_("codeemmanuel").upload(
                filename,
                file_bytes,
                {"content-type": profile_picture.content_type},
            )
            if hasattr(res, "error"):
                logger.error("Error uploading profile picture: %s", res)
                raise HTTPException(
                    status_code=500, detail="Error uploading profile picture"
                )
        except Exception as e:
            logger.error("Failed to save profile picture:%s", str(e))
            profile_picture = None
            raise HTTPException(status_code=500, detail="Error saving profile picture")
    password = str(password)
    hashed_password = hash_password(password)
    new_user = User(
        profile_picture=filename,
        email=email.strip(),
        username=username.strip(),
        password=hashed_password,
        name=name.strip(),
        age=age,
        nationality=nationality.strip() if nationality else None,
    )
    logger.info(f"Registration attempt for username: {username}, email: {email}")
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        send_email_name.delay(
            subject="Registered Successfully",
            body="welcome to Beaut Citi, hope you enjoy your experience, customer support is always available if you need anything, thanks for being a partner",
            to_email=new_user.email,
        )
    except IntegrityError:
        await db.rollback()
        if filename:
            cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleaned, "error"):
                logger.error("Error removing orphaned file: %s", cleaned)
            else:
                logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.error(f"User {username} registration rolled back due to error")
        raise HTTPException(status_code=500, detail="Database Error")
    except Exception as e:
        await db.rollback()
        if filename:
            cleaned = await get_supabase.storage.from_("codeemmanuel").remove(
                [filename]
            )
            if hasattr(cleaned, "error"):
                logger.error("Error removing orphaned file: %s", cleaned)
            else:
                logger.warning("Removed orphaned file after rollback: %s", filename)
        logger.error(f"Error during registration for user {username}: {str(e)}")
        raise HTTPException(status_code=500, detail="internal server error")
    logger.info(f"User {username} registered successfully")
    return StandardResponse(
        status="success",
        message=f"{username} registered successfully",
        data={"username": username.strip()},
    )


async def login(data, response, db):
    user = (
        await db.execute(
            select(User).where(
                User.is_active == True, User.username == data.username.strip()
            )
        )
    ).scalar_one_or_none()
    if not user or not verify_password(data.password, user.password):
        logger.warning(f"Login failed for username: {data.username}")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token_expires = timedelta(minutes=60)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "nationality": user.nationality,
            "name": user.name,
        },
        expires_delta=token_expires,
    )
    refresh_access = create_refresh_tokens(
        {
            "sub": user.username,
            "user_id": user.id,
            "nationality": user.nationality,
            "name": user.name,
        }
    )
    response.set_cookie(
        key="refresh",
        value=refresh_access,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    logger.info(f"User {data.username} logged in successfully")
    return {
        "status": "success",
        "message": f"{data.username} logged in successfully",
        "data": {
            "username": data.username,
            "access_token": access_token,
            "token_type": "bearer",
        },
    }


async def refresh_token(request, response):
    token = request.cookies.get("refresh")
    logger.info("Refresh token attempt")
    if not token:
        logger.warning("Refresh token missing")
        raise HTTPException(status_code=401, detail="missing token")
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh_token":
        logger.warning("Invalid refresh token")
        raise HTTPException(status_code=401, detail="invalid refresh token")
    username = payload.get("sub")
    user_id = payload.get("user_id")
    name = payload.get("name")
    nationality = payload.get("nationality")
    new_access = create_access_token(
        {
            "sub": username,
            "user_id": user_id,
            "nationality": nationality,
            "name": name,
        }
    )
    new_refresh = create_refresh_tokens(
        {
            "sub": username,
            "user_id": user_id,
            "nationality": nationality,
            "name": name,
        }
    )
    response.set_cookie(
        key="refresh", value=new_refresh, httponly=True, samesite="lax", secure=False
    )

    logger.info(f"Refresh token successful for username: {username}")
    return {"access_token": new_access, "token_type": "bearer"}


async def sign_out(request, response, db):
    request.cookies.get("refresh")
    response.delete_cookie("refresh")
    logger.info("User logged out successfully")
    return {"message": "logged out"}
