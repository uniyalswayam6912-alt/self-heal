from fastapi import FastAPI

app = FastAPI(
    title="Self-Heal Authentication Service",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "service": "auth-service",
        "status": "healthy",
    }