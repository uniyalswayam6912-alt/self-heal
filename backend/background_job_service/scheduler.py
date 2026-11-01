import time
from datetime import datetime, timezone

from sqlalchemy import select

from backend.background_job_service.database import SessionLocal
from backend.background_job_service.models import Job
from backend.background_job_service.messaging import enqueue_job


def run_scheduler():
    while True:
        db = SessionLocal()

        try:
            now = datetime.now(timezone.utc)

            jobs = db.scalars(
                select(Job).where(
                    Job.status == "queued",
                    Job.next_retry_at <= now,
                )
            ).all()

            for job in jobs:
                enqueue_job(job.id, job.retry_count)

                job.next_retry_at = None

            db.commit()

        except Exception as exc:
            db.rollback()
            print(f"Scheduler error: {exc}", flush=True)

        finally:
            db.close()

        time.sleep(2)


if __name__ == "__main__":
    run_scheduler()