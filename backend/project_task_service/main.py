
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.project_task_service.database import Base, engine
from backend.project_task_service import models

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.project_task_service.database import SessionLocal
from backend.project_task_service.models import Project, Task

from enum import Enum


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Self-Heal Project & Task Service",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    return {
        "service": "project-task-service",
        "status": "healthy",
    }


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    request: ProjectCreate,
    db: Session = Depends(get_db),
):
    project = Project(
        name=request.name,
        description=request.description,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@app.get("/projects", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.id)).all()


@app.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    project_id: int


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None
    status: TaskStatus
    project_id: int



@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    request: TaskCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, request.project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    task = Task(
        title=request.title,
        description=request.description,
        project_id=request.project_id,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = select(Task).order_by(Task.id)

    if project_id is not None:
        query = query.where(Task.project_id == project_id)

    return db.scalars(query).all()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    request: TaskUpdate,
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    updates = request.model_dump(exclude_unset=True)

    for field, value in updates.items():
        if field == "status" and value is not None:
            value = value.value

        setattr(task, field, value)

    db.commit()
    db.refresh(task)

    return task

