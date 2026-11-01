import json
import time
import logging
from datetime import datetime, timedelta, timezone

from kafka import KafkaConsumer

from backend.background_job_service.database import SessionLocal
from backend.background_job_service.models import Job
from backend.background_job_service.messaging import (
    enqueue_job,
    publish_job_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

def process_job(job_id: int):
    db = SessionLocal()

    try:
        job = db.get(Job, job_id)

        if job is None or job.status != "queued":
            return

        job.status = "in_progress"
        db.commit()
        logger.info("Job %s is now in progress", job.id)

        publish_job_event("job.started", job.id)

        raise NotImplementedError(
            f"No execution handler available for job type: {job.job_type}"
        )

    except Exception as exc:
        db.rollback()

        job = db.get(Job, job_id)

        if job is not None:
            job.retry_count += 1
            job.error_message = str(exc)[:2000]
            logger.error("Job %s failed: %s", job_id, exc)

            # Unsupported job types cannot be fixed by retrying.
            if isinstance(exc, NotImplementedError):
                job.status = "failed"
                job.next_retry_at = None

            elif job.retry_count < job.max_retries:
                delay = 2 ** job.retry_count

                job.status = "queued"
                job.next_retry_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=delay)
                )

                logger.warning(
                    "Job %s scheduled for retry %s/%s after %s seconds",
                    job.id,
                    job.retry_count,
                    job.max_retries,
                    delay,
                )

                db.commit()

                publish_job_event("job.retry_scheduled", job.id)
                return

            else:
                job.status = "failed"
                job.next_retry_at = None

            logger.error(
                "Job %s permanently failed after %s attempts",
                job.id,
                job.retry_count,
            )

            db.commit()

            try:
                publish_job_event("job.failed", job.id)
            except Exception:
                pass

    finally:
        db.close()


def run_worker():
    consumer = KafkaConsumer(
        "background-jobs",
        bootstrap_servers="kafka:9092",
        group_id="background-job-workers",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
    )

    for message in consumer:
        try:
            job_id = int(message.value["job_id"])
            process_job(job_id)
            consumer.commit()

        except Exception as exc:
            logger.exception("Worker encountered an unexpected error")
            time.sleep(2)


if __name__ == "__main__":
    run_worker()