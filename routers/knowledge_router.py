from fastapi import APIRouter, File, Form, Header, Query, UploadFile

from helpers.auth_guard import assert_can_delete_knowledge
from helpers.rag_service import (
    delete_knowledge_document,
    ingest_pdf_document,
    list_knowledge_documents,
    search_knowledge_chunks,
)
from models.knowledge_model import (
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["KnowledgeRAG"])


@router.post("/upload", response_model=KnowledgeDocumentResponse, status_code=201)
async def upload_knowledge_pdf(
    file: UploadFile = File(...),
    parish_id: int = Form(...),
    title: str = Form(""),
    category: str = Form("Geral"),
    description: str = Form(""),
    uploaded_by: str = Form(""),
):
    raw_bytes = await file.read()
    doc = await ingest_pdf_document(
        raw_bytes=raw_bytes,
        filename=file.filename or "documento.pdf",
        parish_id=parish_id,
        title=title,
        category=category,
        description=description,
        uploaded_by=uploaded_by,
    )
    return KnowledgeDocumentResponse(**doc)


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
async def get_knowledge_documents(
    parish_id: int = Query(...),
    category: str | None = Query(default=None),
):
    docs = await list_knowledge_documents(parish_id=parish_id, category=category)
    return [KnowledgeDocumentResponse(**doc) for doc in docs]


@router.delete("/documents/{doc_id}")
async def remove_knowledge_document(
    doc_id: str,
    parish_id: int = Query(...),
    authorization: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    assert_can_delete_knowledge(
        parish_id=parish_id,
        authorization=authorization,
        user_role_header=x_user_role,
    )
    await delete_knowledge_document(doc_id=doc_id, parish_id=parish_id)
    return {"message": "Documento removido da base de conhecimento com sucesso."}


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge_base(payload: KnowledgeSearchRequest):
    search_mode, matches = await search_knowledge_chunks(
        query=payload.query,
        parish_id=payload.parish_id,
        category=payload.category,
        top_k=payload.top_k,
    )
    return KnowledgeSearchResponse(
        query=payload.query,
        search_mode=search_mode,
        matches=matches,
    )
