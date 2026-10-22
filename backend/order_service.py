from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router= APIRouter(prefix= "/orders", tags=["Orders"])

orders= {}


#defining in which format should order arrive, cannot be any format
class OrderRequest(BaseModel):
    product_id: str= Field(min_length=1)
    quantity: int= Field(gt=0)

class OrderResponse(BaseModel):
    order_id: str
    product_id: str
    quantity: str
    status: str

@router.post(
    "/",
    response_model= OrderResponse,
    status_code= status.HTTP_201_CREATED,
)
def create_order(request: OrderRequest):
    order_id= str(uuid4())

    order= {
        "order_id": order_id,
        "product_id": request.product_id,
        "quantity": request.quantity,
        "status": "created",
    }
    orders[order_id]= order
    return order

@router.get("/{order_id}", response_model= OrderResponse)
def get_order(order_id:str):
    order= orders.get(order_id)

    if not order:
        raise HTTPException(
            status_code=404,
            detail= "Order not found",
        )
    return order
