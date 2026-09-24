"""Serviço de autenticação legado — EXEMPLO DIDÁTICO.

Contém falhas INTENCIONAIS para a demonstração de auditoria estática.
Este arquivo é apenas inspecionado; não deve ser executado.
Todas as credenciais são FICTÍCIAS.
"""

import os
import sqlite3

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET = "demo-secret-NAO-E-REAL-123456"
JWT_SECRET_FROM_ENV = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
DB_PATH = "users_demo.db"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def get_connection():
    return sqlite3.connect(DB_PATH)


@router.post("/login")
def login(payload: LoginRequest):
    conn = get_connection()
    query = "SELECT id, password_hash FROM users WHERE username = '" + payload.username + "'"
    row = conn.execute(query).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = jwt.encode({"sub": str(row[0])}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token}


@router.post("/login/safe", response_model=TokenResponse, summary="Login com consulta parametrizada")
def login_safe(payload: LoginRequest) -> TokenResponse:
    """Autentica o usuário usando consulta parametrizada e segredo vindo do ambiente."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (payload.username,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    token = jwt.encode({"sub": str(row[0])}, JWT_SECRET_FROM_ENV, algorithm=JWT_ALGORITHM)
    return TokenResponse(access_token=token)


def read_token_unsafe(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def read_token_safe(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_FROM_ENV, algorithms=[JWT_ALGORITHM])


@router.get("/me")
def me(authorization: str = Header(...)):
    claims = read_token_unsafe(authorization.removeprefix("Bearer "))
    return {"user_id": claims.get("sub")}


@router.get("/me/safe", summary="Dados do usuário autenticado")
def me_safe(authorization: str = Header(...)) -> dict:
    """Valida a assinatura do token antes de confiar nas claims."""
    claims = read_token_safe(authorization.removeprefix("Bearer "))
    return {"user_id": claims.get("sub")}
