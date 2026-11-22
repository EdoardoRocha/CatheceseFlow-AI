import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException
from pymongo import AsyncMongoClient

# Carrega o .env localizado na raiz do módulo AI independentemente de onde o processo for iniciado
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

_client: AsyncMongoClient | None = None
_db = None


async def init() -> None:
    """Inicializa a conexão com o MongoDB e garante os índices das coleções."""
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

    await _db["knowledge_documents"].create_index(
        [("parish_id", 1), ("file_hash", 1)],
        unique=True,
    )
    await _db["knowledge_documents"].create_index([("parish_id", 1), ("category", 1)])

    await _db["knowledge_chunks"].create_index("document_id")
    await _db["knowledge_chunks"].create_index([("parish_id", 1), ("category", 1)])

    await _db["generated_formations"].create_index("parish_id")
    await _db["generated_formations"].create_index("created_at")

    print(f"[Catheces-AI] Conectado ao MongoDB ({db_name}).")


async def _ensure_db():
    global _db
    if _db is None:
        await init()

    if _db is None:
        raise HTTPException(
            status_code=503,
            detail="MONGODB_URI não configurada no arquivo AI/.env.",
        )

    return _db


async def get_summaries_collection():
    """Retorna a coleção lecture_summaries ou inicializa sob demanda."""
    db = await _ensure_db()
    return db["lecture_summaries"]


async def get_knowledge_documents_collection():
    """Retorna a coleção knowledge_documents (metadados dos PDFs RAG)."""
    db = await _ensure_db()
    return db["knowledge_documents"]


async def get_knowledge_chunks_collection():
    """Retorna a coleção knowledge_chunks (fragmentos vetorizados para RAG)."""
    db = await _ensure_db()
    return db["knowledge_chunks"]


async def get_generated_formations_collection():
    """Retorna a coleção generated_formations (roteiros gerados pelo chat para PDF)."""
    db = await _ensure_db()
    return db["generated_formations"]
