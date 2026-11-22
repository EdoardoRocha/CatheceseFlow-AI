import asyncio
import base64
import hashlib
import hmac
from io import BytesIO
import json
import time

from bson import ObjectId
from fastapi.testclient import TestClient
from fpdf import FPDF
from pymongo.errors import OperationFailure


def _make_sample_pdf_bytes(pages_text: list[str]) -> bytes:
    pdf = FPDF()
    for page_text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, page_text)
    return bytes(pdf.output())


def _make_jwt(payload: dict, secret: str) -> str:
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode("utf-8"))
    p = _b64(json.dumps(payload).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), f"{h}.{p}".encode("utf-8"), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64(sig)}"


def test_extract_pdf_pages_and_chunker():
    from helpers.rag_chunker import chunk_pdf_pages, compute_file_hash, extract_pdf_pages

    long_paragraph = "Formacao sobre Eucaristia e partilha fraterna na catequese. " * 25
    pdf_bytes = _make_sample_pdf_bytes([long_paragraph, "Oracao final e envio dos crismandos."])

    pages = extract_pdf_pages(pdf_bytes)
    assert len(pages) == 2
    assert pages[0][0] == 1
    assert pages[1][0] == 2

    chunks = chunk_pdf_pages(pages, chunk_size=300, chunk_overlap=50)
    assert len(chunks) >= 3
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["chunk_index"] == 0
    assert chunks[-1]["page_number"] == 2
    assert len(compute_file_hash(pdf_bytes)) == 64


def test_ingest_pdf_and_reject_duplicate_per_parish(monkeypatch):
    from fastapi import HTTPException
    from helpers import rag_service

    stored_docs: list[dict] = []
    stored_chunks: list[dict] = []

    class FakeInsertResult:
        def __init__(self, inserted_id):
            self.inserted_id = inserted_id

    class FakeDocsCol:
        async def find_one(self, query):
            for doc in stored_docs:
                if (
                    doc["parish_id"] == query.get("parish_id")
                    and doc["file_hash"] == query.get("file_hash")
                ):
                    return doc
            return None

        async def insert_one(self, doc):
            oid = ObjectId()
            stored_docs.append({"_id": oid, **doc})
            return FakeInsertResult(oid)

        async def delete_one(self, query):
            stored_docs[:] = [d for d in stored_docs if d["_id"] != query.get("_id")]

    class FakeChunksCol:
        async def insert_many(self, chunks):
            stored_chunks.extend(chunks)

    class FakeEmbeddings:
        async def aembed_documents(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    async def fake_docs_col():
        return FakeDocsCol()

    async def fake_chunks_col():
        return FakeChunksCol()

    monkeypatch.setattr(rag_service, "get_knowledge_documents_collection", fake_docs_col)
    monkeypatch.setattr(rag_service, "get_knowledge_chunks_collection", fake_chunks_col)

    pdf_bytes = _make_sample_pdf_bytes(["Texto catequetico de Crisma sobre Pentecostes."])

    created = asyncio.run(
        rag_service.ingest_pdf_document(
            raw_bytes=pdf_bytes,
            filename="pentecostes.pdf",
            parish_id=1,
            title="Formacao Pentecostes",
            category="Crisma",
            uploaded_by="Edoardo",
            embeddings=FakeEmbeddings(),
        )
    )
    assert created["title"] == "Formacao Pentecostes"
    assert created["parish_id"] == 1
    assert created["total_pages"] == 1
    assert created["total_chunks"] == 1
    assert len(stored_chunks) == 1

    # Mesma paróquia + mesmo arquivo -> 409
    try:
        asyncio.run(
            rag_service.ingest_pdf_document(
                raw_bytes=pdf_bytes,
                filename="pentecostes.pdf",
                parish_id=1,
                embeddings=FakeEmbeddings(),
            )
        )
        raise AssertionError("Era esperado HTTPException 409 para PDF duplicado na mesma paróquia.")
    except HTTPException as exc:
        assert exc.status_code == 409

    # Outra paróquia pode subir o mesmo arquivo sem conflito
    created_other = asyncio.run(
        rag_service.ingest_pdf_document(
            raw_bytes=pdf_bytes,
            filename="pentecostes.pdf",
            parish_id=2,
            embeddings=FakeEmbeddings(),
        )
    )
    assert created_other["parish_id"] == 2


def test_search_knowledge_chunks_vector_and_cosine_fallback_parish_isolated(monkeypatch):
    from helpers import rag_service

    chunks_data = [
        {
            "document_id": "doc1",
            "document_title": "Eucaristia Paroquia 1",
            "category": "Primeira Comunhão",
            "parish_id": 1,
            "page_number": 2,
            "chunk_index": 0,
            "content": "Pao da Vida e comunhao.",
            "embedding": [1.0, 0.0, 0.0],
        },
        {
            "document_id": "doc2",
            "document_title": "Eucaristia Paroquia 2",
            "category": "Primeira Comunhão",
            "parish_id": 2,
            "page_number": 1,
            "chunk_index": 0,
            "content": "Conteudo restrito da paroquia 2.",
            "embedding": [1.0, 0.0, 0.0],
        },
        {
            "document_id": "doc3",
            "document_title": "Batismo Paroquia 1",
            "category": "Crisma",
            "parish_id": 1,
            "page_number": 3,
            "chunk_index": 1,
            "content": "Dons do Espirito Santo.",
            "embedding": [0.0, 1.0, 0.0],
        },
    ]

    class AsyncListCursor:
        def __init__(self, items):
            self._items = items
            self._idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx >= len(self._items):
                raise StopAsyncIteration
            val = self._items[self._idx]
            self._idx += 1
            return val

    class FakeEmbeddings:
        async def aembed_query(self, text):
            return [1.0, 0.0, 0.0]

    # 1) Teste fallback por cosseno quando $vectorSearch levanta OperationFailure
    class FallbackChunksCol:
        async def aggregate(self, pipeline):
            raise OperationFailure("$vectorSearch index not found")

        def find(self, mongo_filter, projection):
            filtered = [
                c
                for c in chunks_data
                if c["parish_id"] == mongo_filter["parish_id"]
                and ("category" not in mongo_filter or c["category"] == mongo_filter["category"])
            ]
            return AsyncListCursor(filtered)

    async def fake_col_fallback():
        return FallbackChunksCol()

    monkeypatch.setattr(rag_service, "get_knowledge_chunks_collection", fake_col_fallback)
    mode, matches = asyncio.run(
        rag_service.search_knowledge_chunks(
            query="Eucaristia",
            parish_id=1,
            top_k=5,
            embeddings=FakeEmbeddings(),
        )
    )
    assert mode == "cosine_fallback"
    assert len(matches) == 2
    assert all("Paroquia 2" not in m["document_title"] for m in matches)
    assert matches[0]["document_title"] == "Eucaristia Paroquia 1"
    assert matches[0]["score"] == 1.0

    # 2) Teste caminho nativo $vectorSearch
    class VectorChunksCol:
        async def aggregate(self, pipeline):
            assert pipeline[0]["$vectorSearch"]["filter"] == {"parish_id": 1}
            return AsyncListCursor(
                [
                    {
                        "document_id": "doc1",
                        "document_title": "Eucaristia Paroquia 1",
                        "category": "Primeira Comunhão",
                        "page_number": 2,
                        "chunk_index": 0,
                        "content": "Pao da Vida e comunhao.",
                        "score": 0.95,
                    }
                ]
            )

    async def fake_col_vector():
        return VectorChunksCol()

    monkeypatch.setattr(rag_service, "get_knowledge_chunks_collection", fake_col_vector)
    mode_v, matches_v = asyncio.run(
        rag_service.search_knowledge_chunks(
            query="Eucaristia",
            parish_id=1,
            embeddings=FakeEmbeddings(),
        )
    )
    assert mode_v == "vector_search"
    assert matches_v[0]["score"] == 0.95


def test_knowledge_router_upload_list_and_delete_permissions(monkeypatch):
    from helpers import auth_guard
    from routers import knowledge_router
    import server

    client = TestClient(server.app)

    async def fake_ingest(**kwargs):
        return {
            "id": "507f1f77bcf86cd799439011",
            "title": "Crisma 2025",
            "filename": kwargs["filename"],
            "category": kwargs["category"],
            "description": "",
            "parish_id": kwargs["parish_id"],
            "total_pages": 3,
            "total_chunks": 6,
            "uploaded_by": "Edoardo",
            "created_at": "2026-11-22T10:00:00+00:00",
        }

    async def fake_list(parish_id, category=None):
        return [
            {
                "id": "507f1f77bcf86cd799439011",
                "title": "Crisma 2025",
                "filename": "crisma.pdf",
                "category": "Crisma",
                "description": "",
                "parish_id": parish_id,
                "total_pages": 3,
                "total_chunks": 6,
                "uploaded_by": "Edoardo",
                "created_at": "2026-11-22T10:00:00+00:00",
            }
        ]

    deleted_calls: list[tuple[str, int]] = []

    async def fake_delete(doc_id, parish_id):
        deleted_calls.append((doc_id, parish_id))

    monkeypatch.setattr(knowledge_router, "ingest_pdf_document", fake_ingest)
    monkeypatch.setattr(knowledge_router, "list_knowledge_documents", fake_list)
    monkeypatch.setattr(knowledge_router, "delete_knowledge_document", fake_delete)

    upload_resp = client.post(
        "/api/v1/knowledge/upload",
        data={"parish_id": "1", "title": "Crisma 2025", "category": "Crisma"},
        files={"file": ("crisma.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["parish_id"] == 1

    list_resp = client.get("/api/v1/knowledge/documents?parish_id=1")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Permissões com JWT assinado (AUTH_SECRET configurado)
    secret = "segredo_teste_cathecese"
    monkeypatch.setenv("AUTH_SECRET", secret)

    catequista_jwt = _make_jwt(
        {"id": 1, "role": "Catequista", "ParishId": 1, "exp": time.time() + 3600},
        secret,
    )
    other_parish_admin_jwt = _make_jwt(
        {"id": 2, "role": "Admin", "ParishId": 2, "exp": time.time() + 3600},
        secret,
    )
    coord_jwt = _make_jwt(
        {"id": 3, "role": "Coordenador", "ParishId": 1, "exp": time.time() + 3600},
        secret,
    )

    assert (
        client.delete("/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1").status_code
        == 401
    )
    assert (
        client.delete(
            "/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1",
            headers={"Authorization": f"Bearer {catequista_jwt}"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1",
            headers={"Authorization": f"Bearer {other_parish_admin_jwt}"},
        ).status_code
        == 403
    )

    ok_resp = client.delete(
        "/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1",
        headers={"Authorization": f"Bearer {coord_jwt}"},
    )
    assert ok_resp.status_code == 200
    assert deleted_calls == [("507f1f77bcf86cd799439011", 1)]

    # Modo sem AUTH_SECRET usa X-User-Role estritamente para Coordenador/Admin
    monkeypatch.setenv("AUTH_SECRET", "")
    assert (
        client.delete(
            "/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1",
            headers={"X-User-Role": "Catequista"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/api/v1/knowledge/documents/507f1f77bcf86cd799439011?parish_id=1",
            headers={"X-User-Role": "Admin"},
        ).status_code
        == 200
    )
    assert auth_guard is not None
