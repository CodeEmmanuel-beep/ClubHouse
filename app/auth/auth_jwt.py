from datetime import timezone, timedelta, datetime
from jose import jwt
from passlib.context import CryptContext
from fastapi import HTTPException
from dotenv import load_dotenv
import re
import os

load_dotenv()
sk = os.getenv("SECRET_KEY")
if not sk:
    raise RuntimeError("Could not access SECRET_KEY")
SECRET_KEY = sk
al = os.getenv("ALGORITHM")
if not al:
    raise RuntimeError("Could not access ALGORITH")
ALGORITHM = al
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str | int):
    pwd = str(password)
    if len(str(pwd)) < 8:
        raise HTTPException(
            status_code=401,
            detail="weak password, password should be morethan 7 characters",
        )
    if not re.search(r"[A-Za-z]", pwd) or not re.search(r"\d", pwd):
        raise HTTPException(
            status_code=401,
            detail="Weak password: must contain both letters and numbers.",
        )
    return pwd_context.hash(pwd)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    to_encode["type"] = "access_token"
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def create_refresh_tokens(data: dict, expire_days=7):
    to_encode = data.copy()
    to_encode["type"] = "refresh_token"
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode.update({"exp": expire})
    refresh_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return refresh_token
