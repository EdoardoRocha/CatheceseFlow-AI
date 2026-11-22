from datetime import datetime, timezone
import math
import os
from pathlib import Path
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_openai import OpenAIEmbeddings
from pymongo.errors import OperationFailure

from config.database import (
    get_knowledge_chunks_collection,
    get_knowledge_documents_collection,
)
from helpers.rag_chunker import chunk_pdf_pages, compute_file_hash, extract_pdf_pages

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MAX_PDF_BYTES = 15 * 1024 * 1024
VECTOR_INDEX_NAME = "vector_index"


def create_embeddings_client() -> OpenAIEmbeddings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY não configurada no arquivo AI/.env.",
        )
    model_name = (
        os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        or "text-embedding-3-small"
    )
    return OpenAIEmbeddings(model=model_name, api_key=api_key)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calcula similaridade do cosseno em Python puro entre dois vetores."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def _serialize_document(doc: dict) -> dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc["title"],
        "filename": doc["filename"],
        "category": doc.get("category", "Geral"),
        "description": doc.get("description", ""),
        "parish_id": int(doc["parish_id"]),
        "total_pages": int(doc.get("total_pages", 0)),
        "total_chunks": int(doc.get("total_chunks", 0)),
        "uploaded_by": doc.get("uploaded_by", ""),
        "created_at": doc["created_at"],
    }


async def ingest_pdf_document(
    raw_bytes: bytes,
    filename: str,
    parish_id: int,
    title: str = "",
    category: str = "Geral",
    description: str = "",
    uploaded_by: str = "",
    embeddings: OpenAIEmbeddings | None = None,
) -> dict[str, Any]:
    """Extrai texto, gera chunks + embeddings e persiste o PDF indexado para a paróquia."""
    if not filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo com extensão .pdf.",
        )

    if not raw_bytes or len(raw_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail="O arquivo PDF deve ter entre 1 byte e 15 MB.",
        )

    file_hash = compute_file_hash(raw_bytes)
    docs_col = await get_knowledge_documents_collection()
    chunks_col = await get_knowledge_chunks_collection()

    existing = await docs_col.find_one({"parish_id": int(parish_id), "file_hash": file_hash})
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Este PDF já está indexado nesta paróquia com o título '{existing.get('title', filename)}'.",
        )

    try:
        pages = extract_pdf_pages(raw_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível ler o arquivo PDF enviado: {exc}",
        ) from exc

    if not pages:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível extrair texto deste PDF. Envie um PDF com texto selecionável (não apenas imagem escaneada).",
        )

    chunks = chunk_pdf_pages(pages)
    emb_client = embeddings or create_embeddings_client()
    vectors = await emb_client.aembed_documents([item["content"] for item in chunks])

    clean_title = title.strip() or filename.rsplit(".", 1)[0].strip() or filename
    clean_category = category.strip() or "Geral"
    now_iso = datetime.now(timezone.utc).isoformat()

    doc_payload = {
        "title": clean_title,
        "filename": filename,
        "category": clean_category,
        "description": description.strip(),
        "parish_id": int(parish_id),
        "file_hash": file_hash,
        "total_pages": len(pages),
        "total_chunks": len(chunks),
        "uploaded_by": uploaded_by.strip(),
        "created_at": now_iso,
    }

    insert_res = await docs_col.insert_one(doc_payload)
    doc_id = str(insert_res.inserted_id)

    chunk_docs = [
        {
            "document_id": doc_id,
            "document_title": clean_title,
            "category": clean_category,
            "parish_id": int(parish_id),
            "page_number": chunk["page_number"],
            "chunk_index": chunk["chunk_index"],
            "content": chunk["content"],
            "embedding": vector,
            "created_at": now_iso,
        }
        for chunk, vector in zip(chunks, vectors)
    ]

    try:
        await chunks_col.insert_many(chunk_docs)
    except Exception:
        await docs_col.delete_one({"_id": insert_res.inserted_id})
        raise

    doc_payload["_id"] = insert_res.inserted_id
    return _serialize_document(doc_payload)


async def list_knowledge_documents(
    parish_id: int,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Lista os documentos PDF indexados exclusivos da paróquia."""
    docs_col = await get_knowledge_documents_collection()
    mongo_filter: dict[str, Any] = {"parish_id": int(parish_id)}
    if category and category.strip():
        mongo_filter["category"] = category.strip()

    cursor = docs_col.find(mongo_filter).sort("created_at", -1)
    docs = [doc async for doc in cursor]
    return [_serialize_document(doc) for doc in docs]


async def delete_knowledge_document(doc_id: str, parish_id: int) -> None:
    """Remove um documento da paróquia e todos os seus chunks indexados."""
    if not ObjectId.is_valid(doc_id):
        raise HTTPException(status_code=400, detail="Identificador do documento inválido.")

    docs_col = await get_knowledge_documents_collection()
    chunks_col = await get_knowledge_chunks_collection()

    object_id = ObjectId(doc_id)
    existing = await docs_col.find_one({"_id": object_id, "parish_id": int(parish_id)})
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Documento não encontrado nesta paróquia.",
        )

    await chunks_col.delete_many({"document_id": doc_id, "parish_id": int(parish_id)})
    await docs_col.delete_one({"_id": object_id, "parish_id": int(parish_id)})


async def search_knowledge_chunks(
    query: str,
    parish_id: int,
    category: str | None = None,
    top_k: int = 5,
    embeddings: OpenAIEmbeddings | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Busca trechos relevantes no RAG da paróquia via Atlas $vectorSearch com fallback cosseno."""
    safe_top_k = max(1, min(int(top_k), 10))
    clean_query = query.strip()
    if not clean_query:
        return "cosine_fallback", []

    emb_client = embeddings or create_embeddings_client()
    query_vector = await emb_client.aembed_query(clean_query)
    chunks_col = await get_knowledge_chunks_collection()

    base_filter: dict[str, Any] = {"parish_id": int(parish_id)}
    if category and category.strip():
        base_filter["category"] = category.strip()

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(safe_top_k * 10, 50),
                "limit": safe_top_k,
                "filter": base_filter,
            }
        },
        {
            "$project": {
                "_id": 0,
                "document_id": 1,
                "document_title": 1,
                "category": 1,
                "page_number": 1,
                "chunk_index": 1,
                "content": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        cursor = await chunks_col.aggregate(pipeline)
        matches = [doc async for doc in cursor]
        if matches:
            return "vector_search", matches
        # Caso não haja docs retornados apenas porque o índice ainda não existe, verifica se há chunks
        any_chunk = await chunks_col.find_one(base_filter, {"_id": 1})
        if any_chunk is None:
            return "vector_search", []
    except OperationFailure:
        pass
    except Exception as exc:
        if "vectorSearch" not in str(exc) and "$vectorSearch" not in str(exc):
            raise

    # Fallback automático por similaridade do cosseno restrito à paróquia
    cursor = chunks_col.find(
        base_filter,
        {
            "_id": 0,
            "document_id": 1,
            "document_title": 1,
            "category": 1,
            "page_number": 1,
            "chunk_index": 1,
            "content": 1,
            "embedding": 1,
        },
    )
    scored: list[dict[str, Any]] = []
    async for chunk_doc in cursor:
        sim = cosine_similarity(query_vector, chunk_doc.get("embedding") or [])
        scored.append(
            {
                "document_id": chunk_doc["document_id"],
                "document_title": chunk_doc["document_title"],
                "category": chunk_doc.get("category", "Geral"),
                "page_number": int(chunk_doc.get("page_number", 1)),
                "chunk_index": int(chunk_doc.get("chunk_index", 0)),
                "score": round(sim, 4),
                "content": chunk_doc["content"],
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return "cosine_fallback", scored[:safe_top_k]
