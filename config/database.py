import os
from dotenv import load_dotenv
from fastapi import HTTPException
from pymongo import AsyncMongoClient

load_dotenv()

_client: AsyncMongoClient | None = None
_db = None


async def init() -> None:
    """Inicializa a conexão com o MongoDB e garante os índices da coleção."""
    global _client, _db

    uri = os.getenv("MONGODB_URI", "").strip()
    db_name = os.getenv("MONGODB_DB_NAME", "catheceseflow_ai").strip() or "catheceseflow_ai"

    if not uri:
        print(
            "[Catheces-AI] AVISO: MONGODB_URI não configurada no AI/.env. "
            "As rotas que acessam o MongoDB retornarão HTTP 503 até ser configurada."
        )
        return

    _client = AsyncMongoClient(uri)
    _db = _client[db_name]
    await _client.admin.command("ping")
    await _db["lecture_summaries"].create_index("lecture_id", unique=True)
    await _db["lecture_summaries"].create_index("class_id")
    print(f"[Catheces-AI] Conectado ao MongoDB ({db_name}).")


async def get_summaries_collection():
    """Retorna a coleção lecture_summaries ou inicializa sob demanda."""
    global _db
    if _db is None:
        await init()

    if _db is None:
        raise HTTPException(
            status_code=503,
            detail="MONGODB_URI não configurada no arquivo AI/.env.",
        )

    return _db["lecture_summaries"]
