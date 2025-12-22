from app.core.celery_config import celery_app
from app.core.async_config import AsyncSessionLocal
from app.models_sql import Task
from sqlalchemy import select, or_
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import requests
from sqlalchemy.orm import selectinload
from app.log.logger import get_loggers

load_dotenv()
API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER = os.getenv("SENDGRID_SENDER")

logger = get_loggers("celery")


@celery_app.task(name="app.task.send_email", queue="email")
def send_email_name(subject: str, body: str, to_email: str):
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = {
        "personalizations": [{"to": [{"email": to_email}], "subject": subject}],
        "from": {"email": SENDER},
        "content": [{"type": "text/plain", "value": body}],
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        print(f"respomse: {response.status_code},  body: {response.text}")
    except Exception as e:
        print(f"failure: {e}")


async def execute_task_async():
    async with AsyncSessionLocal() as db:
        try:

            now = datetime.now(timezone.utc)
            worker = (
                (
                    await db.execute(
                        select(Task)
                        .options(selectinload(Task.user))
                        .where(
                            Task.complete.is_(False),
                            Task.status == "pending",
                        )
                    )
                )
                .scalars()
                .all()
            )

            logger.info(f"Found {len(worker)} tasks to expire")
            for task in worker:
                target = datetime.combine(
                    task.day_of_target, datetime.min.time(), tzinfo=timezone.utc
                )
                if target < now:
                    task.status = "expired"
                    send_email_name.delay(
                        subject="expired deadline",
                        body=f"sorry, your scheduled task with target, '{task.target}' has expired without accomplishment, wish you more strength next time",
                        to_email=task.user.email,
                    )
                await db.commit()
                logger.info("Database commit successful for expired tasks")
        except Exception as e:
            print(f"exception, {e}")
            await db.rollback()
            logger.info("Database rollback executed for expired tasks")


async def done_task_async():
    async with AsyncSessionLocal() as db:
        try:
            done = (
                (
                    await db.execute(
                        select(Task)
                        .options(selectinload(Task.user))
                        .where(
                            Task.complete.is_(True),
                            or_(Task.status == "pending", Task.status.is_(None)),
                        )
                    )
                )
                .scalars()
                .all()
            )
            logger.info(f"Found {len(done)} tasks accomplished before deadline")
            for task in done:
                task.status = "Accomplished"
                send_email_name.delay(
                    subject="Task accomplished!",
                    body=f"congratulations are in other, your task, with Task ID '{task.id}', and target '{task.target}', have been accomplished before the deadline, this shows how commited you are, keep it up, cheers",
                    to_email=task.user.email,
                )
                logger.info(f"Task {task.id} marked as accomplished and email queued")
            await db.commit()
            logger.info("Database commit successful for accomplished tasks")
        except Exception as e:
            print(f"exception, {e}")
            await db.rollback()
            logger.warning("Database rollback executed for accomplished tasks")
