from uuid import uuid4

from fastapi import APIRouter,HTTPException, status
from pydantic import BaseModel, Field

router= APIRouter(prefix="/payments", tags= ["Payments"])

payments={}

class PaymentRequest(BaseModel):
    order_id:str = Field(min_length=1)
    amount:float = Field(gt=0)

class PaymentResponse(BaseModel):
    payment_id:str
    order_id:str
    amount:float
    status:str

@router.post("/", response_model= PaymentResponse, status_code= status.HTTP_201_CREATED,)

def create_payment(request:PaymentRequest):
    payment_id= str(uuid4())

    payment={
        "payment_id":payment_id,
        "order_id": request.order_id,
        "amount": request.amount,
        "status": "completed",
    }

    payments[payment_id]= payment
    return payment

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id:str):
    payment= payments.get(payment_id)

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment



