import os
import smtplib
from email.message import EmailMessage


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_email(recipient: str, subject: str, body: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError("SMTP credentials are not configured")

    email = EmailMessage()
    email["From"] = SMTP_USER
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(email)