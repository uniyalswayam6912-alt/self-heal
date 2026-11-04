from contextlib import asynccontextmanager
import json
import httpx
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime
from backend.integration_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.integration_service.models import Integration, IntegrationLog
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from backend.integration_service.api_client import (
    send_api_request,
    send_api_request_with_retry,
)
from typing import Literal
from pydantic import HttpUrl
from backend.integration_service.webhook_service import verify_webhook_signature
from backend.integration_service.messaging import publish_webhook_event
from backend.integration_service.security import (
    encrypt_credential,
    decrypt_credential,
)

from backend.integration_service.oauth_service import refresh_oauth_token

from sqlalchemy import select, func


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Self-Heal Integration Service",
    version="0.1.0",
    lifespan=lifespan,
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=100)
    base_url: HttpUrl

class IntegrationCredentialsUpdate(BaseModel):
    api_key: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    oauth_token_url: HttpUrl | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None

class IntegrationResponse(BaseModel):
    id: int
    name: str
    platform: str
    base_url: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

@app.post(
    "/integrations",
    response_model=IntegrationResponse,
    status_code=201,
)
def create_integration(
    request: IntegrationCreate,
    db: Session = Depends(get_db),
):
    integration = Integration(
        name=request.name,
        platform=request.platform,
        base_url=str(request.base_url),
        status="disconnected",
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration


@app.get(
    "/integrations",
    response_model=list[IntegrationResponse],
)
def get_integrations(
    db: Session = Depends(get_db),
):
    integrations = db.scalars(
        select(Integration).order_by(Integration.created_at.desc())
    ).all()

    return integrations


@app.get("/integrations/{integration_id}",response_model=IntegrationResponse)
def get_integration(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    return integration



@app.put("/integrations/{integration_id}",response_model=IntegrationResponse)
def update_integration(
    integration_id: int,
    request: IntegrationCreate,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    integration.name = request.name
    integration.platform = request.platform
    integration.base_url = str(request.base_url)

    db.commit()
    db.refresh(integration)

    return integration



@app.patch("/integrations/{integration_id}/disconnect",response_model=IntegrationResponse)
def disconnect_integration(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    integration.status = "disconnected"

    db.commit()
    db.refresh(integration)

    return integration



@app.patch("/integrations/{integration_id}/connect", response_model=IntegrationResponse)
def connect_integration(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    integration.status = "connected"

    db.commit()
    db.refresh(integration)

    return integration


@app.post("/integrations/{integration_id}/check")
def check_integration_connection(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    response = send_api_request(
        base_url=integration.base_url,
        method="GET",
        endpoint="",
    )

    integration.status = (
        "connected" if response["success"] else "disconnected"
    )

    db.commit()
    db.refresh(integration)

    return {
        "integration_id": integration.id,
        "platform": integration.platform,
        "status": integration.status,
        "response": response,
    }


@app.post("/integrations/{integration_id}/request")
def send_integration_request(
    integration_id: int,
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
    endpoint: str = Query(min_length=1, max_length=500),
    payload: dict | None = None,
    headers: dict | None = None,
    params: dict | None = None,
    timeout: float = Query(default=10.0, gt=0, le=60),
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    if integration.status != "connected":
        raise HTTPException(
            status_code=400,
            detail="Integration is not connected",
        )

    try:
        headers = dict(headers or {})

        if "Authorization" not in headers:
            if integration.api_key:
                headers["Authorization"] = (
                    f"Bearer {decrypt_credential(integration.api_key)}"
                )

            elif integration.access_token:
                headers["Authorization"] = (
                    f"Bearer {decrypt_credential(integration.access_token)}"
                )

        response = send_api_request_with_retry(
            base_url=integration.base_url,
            method=method,
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            params=params,
            timeout=timeout,
        )

        if (
            response["status_code"] == 401
            and integration.access_token
            and integration.refresh_token
            and integration.oauth_token_url
            and integration.oauth_client_id
            and integration.oauth_client_secret
        ):
            token_response = refresh_oauth_token(
                token_url=integration.oauth_token_url,
                refresh_token=decrypt_credential(integration.refresh_token),
                client_id=integration.oauth_client_id,
                client_secret=decrypt_credential(
                    integration.oauth_client_secret
                ),
            )

            new_access_token = token_response.get("access_token")

            if not new_access_token:
                raise HTTPException(
                    status_code=502,
                    detail="OAuth provider did not return an access token",
                )

            integration.access_token = encrypt_credential(new_access_token)

            new_refresh_token = token_response.get("refresh_token")

            if new_refresh_token:
                integration.refresh_token = encrypt_credential(
                    new_refresh_token
                )

            db.commit()

            headers["Authorization"] = f"Bearer {new_access_token}"

            response = send_api_request(
                base_url=integration.base_url,
                method=method,
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                params=params,
                timeout=timeout,
            )

        integration.last_response_time_ms = response["response_time_ms"]

        if response["status_code"] == 429:
            integration.last_error = "External API rate limit exceeded"

        elif not response["success"]:
            integration.last_error = (
                f"External API returned HTTP {response['status_code']}"
            )

        else:
            integration.last_error = None
            integration.last_error_at = None

        if integration.last_error:
            integration.last_error_at = datetime.now(timezone.utc)
            integration.last_retry_count = response.get("retry_count", 0)
        else:
            integration.last_retry_count = 0

        log = IntegrationLog(
            integration_id=integration.id,
            method=method,
            endpoint=endpoint,
            status_code=response["status_code"],
            response_time_ms=response["response_time_ms"],
            success=response["success"],
            error_message=integration.last_error,
        )

        db.add(log)
        db.commit()

        return {
            "integration_id": integration.id,
            "platform": integration.platform,
            "response": response,
        }

    except httpx.TimeoutException as error:
        integration.last_error = "External API request timed out"
        integration.last_error_at = datetime.now(timezone.utc)
        integration.last_retry_count = getattr(error, "retry_count", 0)

        db.add(
            IntegrationLog(
                integration_id=integration.id,
                method=method,
                endpoint=endpoint,
                success=False,
                error_message=integration.last_error,
            )
        )

        db.commit()

        raise HTTPException(
            status_code=504,
            detail="External API request timed out",
        )

    except httpx.RequestError as error:
        integration.last_error = "External API connection failed"
        integration.last_error_at = datetime.now(timezone.utc)
        integration.last_retry_count = getattr(error, "retry_count", 0)

        db.add(
            IntegrationLog(
                integration_id=integration.id,
                method=method,
                endpoint=endpoint,
                success=False,
                error_message=integration.last_error,
            )
        )

        db.commit()

        raise HTTPException(
            status_code=502,
            detail="External API connection failed",
        )

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="External API request failed",
        )



@app.post("/webhooks/{platform}")
async def receive_webhook(
    platform: str,
    request: Request,
    db: Session = Depends(get_db),
):
    integration = db.scalars(
        select(Integration).where(
            Integration.platform == platform,
            Integration.status == "connected",
        )
    ).first()

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Connected integration not found",
        )

    if not integration.webhook_secret:
        raise HTTPException(
            status_code=400,
            detail="Webhook secret is not configured",
        )

    signature = request.headers.get("X-Webhook-Signature")

    if not signature:
        raise HTTPException(
            status_code=401,
            detail="Webhook signature is missing",
        )

    payload = await request.body()

    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Webhook payload cannot be empty",
        )

    if not verify_webhook_signature(
        payload=payload,
        signature=signature,
        secret=integration.webhook_secret,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    event = json.loads(payload)

    publish_webhook_event({
        "integration_id": integration.id,
        "platform": integration.platform,
        "event": event,
    })

    return {
        "message": "Webhook received successfully",
        "integration_id": integration.id,
        "platform": integration.platform,
        "event": event,
    }


@app.patch("/integrations/{integration_id}/credentials")
def update_integration_credentials(
    integration_id: int,
    request: IntegrationCredentialsUpdate,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    if request.api_key is not None:
        integration.api_key = encrypt_credential(request.api_key)

    if request.access_token is not None:
        integration.access_token = encrypt_credential(request.access_token)

    if request.refresh_token is not None:
        integration.refresh_token = encrypt_credential(request.refresh_token)

    if request.oauth_token_url is not None:
        integration.oauth_token_url = str(request.oauth_token_url)

    if request.oauth_client_id is not None:
        integration.oauth_client_id = request.oauth_client_id

    if request.oauth_client_secret is not None:
        integration.oauth_client_secret = encrypt_credential(
            request.oauth_client_secret
        )

    db.commit()
    db.refresh(integration)

    return {
        "message": "Integration credentials updated successfully",
        "integration_id": integration.id,
    }


@app.post("/integrations/{integration_id}/refresh-token")
def refresh_integration_access_token(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    if not all([
        integration.oauth_token_url,
        integration.oauth_client_id,
        integration.oauth_client_secret,
        integration.refresh_token,
    ]):
        raise HTTPException(
            status_code=400,
            detail="OAuth configuration is incomplete",
        )

    try:
        token_response = refresh_oauth_token(
            token_url=integration.oauth_token_url,
            refresh_token=decrypt_credential(integration.refresh_token),
            client_id=integration.oauth_client_id,
            client_secret=decrypt_credential(
                integration.oauth_client_secret
            ),
        )

        new_access_token = token_response.get("access_token")

        if not new_access_token:
            raise HTTPException(
                status_code=502,
                detail="OAuth provider did not return an access token",
            )

        integration.access_token = encrypt_credential(new_access_token)

        new_refresh_token = token_response.get("refresh_token")

        if new_refresh_token:
            integration.refresh_token = encrypt_credential(
                new_refresh_token
            )

        db.commit()

        return {
            "message": "OAuth access token refreshed successfully",
            "integration_id": integration.id,
        }

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="OAuth token refresh failed",
        )


@app.get("/integrations/{integration_id}/logs")
def get_integration_logs(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    logs = db.scalars(
        select(IntegrationLog)
        .where(IntegrationLog.integration_id == integration_id)
        .order_by(IntegrationLog.created_at.desc())
    ).all()

    return logs


@app.get("/integrations/{integration_id}/monitoring")
def get_integration_monitoring(
    integration_id: int,
    db: Session = Depends(get_db),
):
    integration = db.get(Integration, integration_id)

    if integration is None:
        raise HTTPException(
            status_code=404,
            detail="Integration not found",
        )

    total_requests = db.scalar(
        select(func.count(IntegrationLog.id)).where(
            IntegrationLog.integration_id == integration_id
        )
    )

    successful_requests = db.scalar(
        select(func.count(IntegrationLog.id)).where(
            IntegrationLog.integration_id == integration_id,
            IntegrationLog.success.is_(True),
        )
    )

    failed_requests = db.scalar(
        select(func.count(IntegrationLog.id)).where(
            IntegrationLog.integration_id == integration_id,
            IntegrationLog.success.is_(False),
        )
    )

    return {
        "integration_id": integration.id,
        "platform": integration.platform,
        "connection_status": integration.status,
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "last_response_time_ms": integration.last_response_time_ms,
        "last_error": integration.last_error,
        "last_error_at": integration.last_error_at,
        "last_retry_count": integration.last_retry_count,
    }