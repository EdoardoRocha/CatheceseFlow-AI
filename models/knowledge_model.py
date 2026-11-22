from typing import Literal
from pydantic import BaseModel, Field

KnowledgeCategory = Literal["Geral", "Primeira Comunhão", "Perseverança", "Crisma"]


class KnowledgeDocumentResponse(BaseModel):
    id: str
    title: str
    filename: str
    category: str
    description: str = ""
    parish_id: int
    total_pages: int
    total_chunks: int
    uploaded_by: str = ""
    created_at: str


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    parish_id: int
    category: str | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class KnowledgeChunkMatch(BaseModel):
    document_id: str
    document_title: str
    category: str
    page_number: int
    chunk_index: int
    score: float
    content: str


class KnowledgeSearchResponse(BaseModel):
    query: str
    search_mode: Literal["vector_search", "cosine_fallback"]
    matches: list[KnowledgeChunkMatch] = Field(default_factory=list)
