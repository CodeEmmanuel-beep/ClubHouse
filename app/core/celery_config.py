from celery import Celery
from app.core.config import settings
import ssl


celery_app = Celery(
    "worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.core.celery_app"],
)

if settings.REDIS_URL.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


celery_app.conf.update(
    beat_schedule={
        "execute-worker-every-1-minute": {
            "task": "app.core.celery_app.execute_task",
            "schedule": 200.0,
        },
        "mark-done": {
            "task": "app.core.celery_app.done_task",
            "schedule": 30.0,
        },
    },
)
