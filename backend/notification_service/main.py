import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.notification_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.notification_service.models import Notification

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Self-Heal Notification Service",
    version="0.1.0",
    lifespan=lifespan,
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class NotificationCreate(BaseModel):
    user_id: int
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime

def build_notification_response(
    notification: Notification,
) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        user_id=notification.user_id,
        title=notification.title,
        message=notification.message,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )

@app.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_notification(
    request: NotificationCreate,
    db: Session = Depends(get_db),
):
    notification = Notification(
        user_id=request.user_id,
        title=request.title,
        message=request.message,
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    return build_notification_response(notification)


@app.get(
    "/notifications/user/{user_id}",
    response_model=list[NotificationResponse],
)
def get_user_notifications(
    user_id: int,
    db: Session = Depends(get_db),
):
    notifications = db.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
    ).all()

    return [
        build_notification_response(notification)
        for notification in notifications
    ]


@app.get(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
)
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = db.get(Notification, notification_id)

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return build_notification_response(notification)



@app.patch("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = db.get(Notification, notification_id)

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = True

    db.commit()
    db.refresh(notification)

    return build_notification_response(notification)


@app.patch("/notifications/{notification_id}/unread")
def mark_notification_as_unread(
    notification_id: int,
    db: Session = Depends(get_db),
):
    notification = db.get(Notification, notification_id)

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = False

    db.commit()
    db.refresh(notification)

    return build_notification_response(notification)

