
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from fastapi import Depends

app = FastAPI(
    title="Self-Heal Authentication Service",
    version="0.2.0",
)

JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 30

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Temporary storage; PostgreSQL comes later.
users = {}


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    email: EmailStr
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


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

    users[email] = {
        "email": email,
        "hashed_password": password_hash.hash(request.password),
    }

    return UserResponse(
        email=email,
        message="User registered successfully",
    )


@app.post("/login", response_model=TokenResponse)
def login_user(request: UserLogin):
    email = str(request.email).lower()
    user = users.get(email)

    if user is None or not password_hash.verify(
        request.password,
        user["hashed_password"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    return TokenResponse(access_token=token)


@app.get("/me")
def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        email = payload["sub"]

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "email": email,
        "message": "You are authenticated",
    }
