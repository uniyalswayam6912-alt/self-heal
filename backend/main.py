from fastapi import FastAPI

from backend.order_service import router as order_router
from backend.payment_service import router as payment_router
from backend.inventory_service import router as inventory_router

app= FastAPI(title= "Self-Heal API")

app.include_router(order_router)
app.include_router(payment_router)
app.include_router(inventory_router)

@app.get("/")
def home():
    return {"message": "Self-Heal backend API is running!"}

