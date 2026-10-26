
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash

app = FastAPI(
    title="Self-Heal Authentication Service",
    version="0.1.0",
)

password_hash = PasswordHash.recommended()

# Temporary storage. We will replace this with PostgreSQL later.
users = {}


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    email: EmailStr
    message: str


@app.get("/health")
def health_check():
    return {
        "service": "auth-service",
        "status": "healthy",
    }


@app.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(request: UserRegister):
    email = str(request.email).lower()

    if email in users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    hashed_password = password_hash.hash(request.password)

    users[email] = {
        "email": email,
        "hashed_password": hashed_password,
    }

    return UserResponse(
        email=email,
        message="User registered successfully",
    )
