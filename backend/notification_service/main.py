import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import threading



from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.notification_service.email_service import send_email

from backend.notification_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.notification_service.models import Notification

from backend.notification_service.retry_scheduler import (
    retry_failed_notifications,
)

from backend.notification_service.messaging import (
    consume_notification_events,
    kafka_consumer,
    publish_dead_letter_event,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    listener_thread = threading.Thread(
        target=notification_event_listener,
        daemon=True,
    )
    listener_thread.start()

    retry_thread = threading.Thread(
        target=retry_failed_notifications,
        daemon=True,
    )
    retry_thread.start()

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

def notification_event_listener():
    for kafka_message in consume_notification_events():
        db = SessionLocal()

        try:
            event = kafka_message.value

            notification = Notification(
                user_id=event["user_id"],
                recipient_email=event.get("recipient_email"),
                title=event["title"],
                message=event["message"],
                delivery_status="pending",
            )

            db.add(notification)
            db.commit()
            db.refresh(notification)

            if notification.recipient_email:
                send_email(
                    recipient=notification.recipient_email,
                    subject=notification.title,
                    body=notification.message,
                )

            notification.delivery_status = "delivered"
            db.commit()

            kafka_consumer.commit()

        except Exception as error:
            db.rollback()

            if "notification" in locals():
                notification.retry_count += 1
                notification.error_message = str(error)

                if notification.retry_count <= notification.max_retries:
                    delay = 2 ** notification.retry_count

                    notification.delivery_status = "pending"
                    notification.next_retry_at = (
                        datetime.now(timezone.utc)
                        + timedelta(seconds=delay)
                    )
                else:
                    notification.delivery_status = "failed"
                    notification.next_retry_at = None

                    publish_dead_letter_event({
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "recipient_email": notification.recipient_email,
                    "title": notification.title,
                    "message": notification.message,
                    "retry_count": notification.retry_count,
                    "error_message": notification.error_message,
                    })

                db.add(notification)
                db.commit()

        finally:
            db.close()

class NotificationCreate(BaseModel):
    user_id: int
    recipient_email: str | None = None
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1)


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    recipient_email: str | None
    title: str
    message: str
    is_read: bool
    delivery_status: str
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None
    error_message: str | None
    created_at: datetime

def build_notification_response(
    notification: Notification,
) -> NotificationResponse:
    return NotificationResponse(
        id=notification.id,
        user_id=notification.user_id,
        recipient_email=notification.recipient_email,
        title=notification.title,
        message=notification.message,
        is_read=notification.is_read,
        delivery_status=notification.delivery_status,
        retry_count=notification.retry_count,
        max_retries=notification.max_retries,
        next_retry_at=notification.next_retry_at,
        error_message=notification.error_message,
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
        recipient_email=request.recipient_email,
        title=request.title,
        message=request.message,
        delivery_status="pending",
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    if notification.recipient_email:
        send_email(
            recipient=notification.recipient_email,
            subject=notification.title,
            body=notification.message,
        )

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

