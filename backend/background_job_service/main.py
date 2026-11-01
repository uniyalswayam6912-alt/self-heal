import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.background_job_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.background_job_service.models import Job

from backend.background_job_service.messaging import (
    enqueue_job,
    publish_job_event,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Self-Heal Background Job Service",
    version="0.2.0",
    lifespan=lifespan,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=100)
    source_service: str = Field(min_length=1, max_length=100)
    input_data: dict | None = None


class JobStatusUpdate(BaseModel):
    status: str = Field(
        pattern="^(queued|in_progress|completed|failed|cancelled)$"
    )
    result: str | None = None
    error_message: str | None = None



class JobResponse(BaseModel):
    id: int
    job_type: str
    source_service: str
    status: str
    input_data: dict | None
    result: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None


def build_job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        job_type=job.job_type,
        source_service=job.source_service,
        status=job.status,
        input_data=(
            json.loads(job.input_data)
            if job.input_data is not None
            else None
        ),
        result=job.result,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        retry_count=job.retry_count,
        max_retries=job.max_retries,
        next_retry_at=job.next_retry_at,
    )




@app.get("/health")
def health_check():
    from backend.background_job_service.messaging import kafka_producer

    kafka_status = "healthy"

    try:
        if not kafka_producer.bootstrap_connected():
            kafka_status = "unhealthy"
    except Exception:
        kafka_status = "unhealthy"

    return {
        "service": "background-job-service",
        "status": kafka_status,
        "dependencies": {
            "kafka": kafka_status,
        },
    }



@app.post(
    "/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    request: JobCreate,
    db: Session = Depends(get_db),
):
    job = Job(
        job_type=request.job_type,
        source_service=request.source_service,
        status="queued",
        input_data=(
            json.dumps(request.input_data)
            if request.input_data is not None
            else None
        ),
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_job(job.id)
    publish_job_event("job.created", job.id)

    return build_job_response(job)


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.id)).all()

    return [
    build_job_response(job)
    for job in jobs
    ]


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return build_job_response(job)


@app.patch("/jobs/{job_id}/status", response_model=JobResponse)
def update_job_status(
    job_id: int,
    request: JobStatusUpdate,
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    job.status = request.status

    if request.result is not None:
        job.result = request.result

    if request.error_message is not None:
        job.error_message = request.error_message

    db.commit()
    db.refresh(job)

    publish_job_event(
        f"job.{job.status}",
        job.id,
    )

    return build_job_response(job)


@app.get("/jobs/metrics")
def get_job_metrics(
    db: Session = Depends(get_db),
):
    job_counts = db.execute(
        select(
            Job.status,
            func.count(Job.id),
        ).group_by(Job.status)
    ).all()

    counts = {
        "queued": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }

    for job_status, count in job_counts:
        if job_status in counts:
            counts[job_status] = count

    return {
        "total_jobs": sum(counts.values()),
        "jobs_by_status": counts,
    }