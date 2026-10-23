
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/inventory", tags=["Inventory"])

# Temporary in-memory product stock
inventory = {
    "LAPTOP-101": 10,
    "PHONE-201": 20,
    "HEADPHONES-301": 15,
}


class StockRequest(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class StockResponse(BaseModel):
    product_id: str
    available_quantity: int
    status: str


@router.get("/{product_id}", response_model=StockResponse)
def get_stock(product_id: str):
    if product_id not in inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return {
        "product_id": product_id,
        "available_quantity": inventory[product_id],
        "status": "available" if inventory[product_id] > 0 else "out_of_stock",
    }


@router.post("/reserve", response_model=StockResponse)
def reserve_stock(request: StockRequest):
    if request.product_id not in inventory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    available = inventory[request.product_id]

    if available < request.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient stock",
        )

    inventory[request.product_id] -= request.quantity
    remaining = inventory[request.product_id]

    return {
        "product_id": request.product_id,
        "available_quantity": remaining,
        "status": "available" if remaining > 0 else "out_of_stock",
    }
