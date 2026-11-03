import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.notification_service.database import SessionLocal
from backend.notification_service.models import Notification
from backend.notification_service.email_service import send_email
from backend.notification_service.messaging import publish_dead_letter_event

def retry_failed_notifications():
    while True:
        db = SessionLocal()

        try:
            now = datetime.now(timezone.utc)

            notifications = db.scalars(
                select(Notification).where(
                    Notification.delivery_status == "pending",
                    Notification.next_retry_at <= now,
                    Notification.recipient_email.is_not(None),
                )
            ).all()

            for notification in notifications:
                try:
                    send_email(
                        recipient=notification.recipient_email,
                        subject=notification.title,
                        body=notification.message,
                    )

                    notification.delivery_status = "delivered"
                    notification.next_retry_at = None
                    notification.error_message = None

                except Exception as error:
                    notification.retry_count += 1
                    notification.error_message = str(error)

                    if notification.retry_count <= notification.max_retries:
                        delay = 2 ** notification.retry_count
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
                        
                db.commit()

        except Exception:
            db.rollback()

        finally:
            db.close()

        time.sleep(2)