from app.core.celery_config import celery_app
from app.core.scheduler import execute_task_async, done_task_async
from app.utils.celery_utils import run_async


@celery_app.task
def execute_task():
    run_async(execute_task_async())


@celery_app.task
def done_task():
    run_async(done_task_async())
