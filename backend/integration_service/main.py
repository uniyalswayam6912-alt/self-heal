from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field
from backend.integration_service.database import (
    Base,
    SessionLocal,
    engine,
)
from backend.integration_service.models import Integration
from fastapi import Depends, FastAPI, HTTPException


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
    base_url: str = Field(min_length=1, max_length=500)


@app.post("/integrations", status_code=201)
def create_integration(
    request: IntegrationCreate,
    db: Session = Depends(get_db),
):
    integration = Integration(
        name=request.name,
        platform=request.platform,
        base_url=request.base_url,
        status="disconnected",
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration


@app.get("/integrations")
def get_integrations(
    db: Session = Depends(get_db),
):
    integrations = db.scalars(
        select(Integration).order_by(Integration.created_at.desc())
    ).all()

    return integrations


@app.get("/integrations/{integration_id}")
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



@app.put("/integrations/{integration_id}")
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
    integration.base_url = request.base_url

    db.commit()
    db.refresh(integration)

    return integration



@app.patch("/integrations/{integration_id}/disconnect")
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



@app.patch("/integrations/{integration_id}/connect")
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



