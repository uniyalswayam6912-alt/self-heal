from contextlib import asynccontextmanager
import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime
from backend.integration_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.integration_service.models import Integration
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from backend.integration_service.api_client import send_api_request
from typing import Literal
from pydantic import HttpUrl
from backend.integration_service.webhook_service import verify_webhook_signature
from backend.integration_service.messaging import publish_webhook_event

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
        response = send_api_request(
            base_url=integration.base_url,
            method=method,
            endpoint=endpoint,
            headers=headers,
            payload=payload,
            params=params,
        )

        return {
            "integration_id": integration.id,
            "platform": integration.platform,
            "response": response,
        }

    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"External API request failed: {str(error)}",
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