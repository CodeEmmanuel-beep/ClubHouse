from app.api.v1.routes import (
    comments,
    participants,
    tasks_sql,
    blog,
    auth,
    profile,
    messaging,
    share,
    reactions,
    group,
    group_tasks,
    opinions,
)
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes.web import router as web_router
from fastapi import Request, FastAPI, HTTPException
from pydantic import ValidationError
import uvicorn
import os
import time
from app.log.logger import get_loggers
from app.exceptions import (
    make_global_exception_handler,
    make_http_exception_handler,
    make_validation_exception_handler,
)
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

app = FastAPI(title="club_house", version="1.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/images", StaticFiles(directory="images"), name="images")


@app.middleware("http")
async def log_request(request: Request, call_next):
    start = time.time()
    try:
        process = await call_next(request)
    except Exception as exc:
        duration = time.time() - start
        logger = get_loggers("requests_errors")
        logger.error(
            f"{request.method}  {request.url.path} -error:{exc} - Duration: {duration:.4f}s"
        )
        raise
    duration = time.time() - start
    logger = get_loggers("requests_server")
    logger.info(
        f"{request.method}  {request.url.path} - status:{process.status_code} - Duration: {duration:.4f}s"
    )
    return process


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(web_router)
app.include_router(messaging.router)
app.include_router(tasks_sql.router)
app.include_router(blog.router)
app.include_router(comments.router)
app.include_router(reactions.router)
app.include_router(share.router)
app.include_router(group.router)
app.include_router(group_tasks.router)
app.include_router(participants.router)
app.include_router(opinions.router)
app.add_exception_handler(HTTPException, make_http_exception_handler())
app.add_exception_handler(Exception, make_global_exception_handler())
app.add_exception_handler(ValidationError, make_validation_exception_handler())


@app.get("/", include_in_schema=False)
def home_page():
    return {
        "message": "Welcome to Club House API. Visit /docs to explore the endpoints."
    }


load_dotenv()
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
