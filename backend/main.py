
from fastapi import FastAPI

app = FastAPI(title="Self-Heal Platform")


@app.get("/")
def home():
    return {
        "message": "Self-Heal Enterprise SaaS Platform is running!"
    }
