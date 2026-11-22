import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException

_AI_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_BACKEND_ENV_PATH = Path(__file__).resolve().parent.parent.parent / "Backend" / ".env"

load_dotenv(_AI_ENV_PATH, override=False)
if _BACKEND_ENV_PATH.exists():
    load_dotenv(_BACKEND_ENV_PATH, override=False)

_ALLOWED_DELETE_ROLES = {"admin", "coordenador"}


def _b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def verify_hs256_jwt(token: str, secret: str) -> dict[str, Any] | None:
    """Valida assinatura HS256 e expiração de um JWT emitido pelo Backend."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        if header.get("alg") != "HS256":
            return None

        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")

        if not hmac.compare_digest(signature_b64, expected_b64):
            return None

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if not isinstance(payload, dict):
            return None

        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and time.time() >= exp:
            return None

        return payload
    except Exception:
        return None


def assert_can_delete_knowledge(
    parish_id: int,
    authorization: str | None = None,
    user_role_header: str | None = None,
) -> None:
    """Garante que apenas Coordenadores ou Administradores da paróquia excluam PDFs do RAG."""
    auth_secret = os.getenv("AUTH_SECRET", "").strip()
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if auth_secret:
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Autenticação obrigatória para excluir documentos da base de conhecimento.",
            )

        payload = verify_hs256_jwt(token, auth_secret)
        if payload is None:
            raise HTTPException(
                status_code=401,
                detail="Token de autenticação inválido ou expirado.",
            )

        role = str(payload.get("role", "")).strip().lower()
        if role not in _ALLOWED_DELETE_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Apenas Coordenadores e Administradores podem excluir PDFs da base de conhecimento.",
            )

        token_parish = payload.get("ParishId")
        if token_parish is not None and int(token_parish) != int(parish_id):
            raise HTTPException(
                status_code=403,
                detail="Acesso negado: o documento pertence a outra paróquia.",
            )
        return

    normalized_role = str(user_role_header or "").strip().lower()
    if normalized_role not in _ALLOWED_DELETE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Apenas Coordenadores e Administradores podem excluir PDFs da base de conhecimento.",
        )
