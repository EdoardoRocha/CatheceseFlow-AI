from typing import Literal
from pydantic import BaseModel, Field


class StructuredSummary(BaseModel):
    title: str = Field(description="Título claro e acolhedor do resumo da formação")
    objective: str = Field(description="Objetivo espiritual e pedagógico principal do encontro")
    key_points: list[str] = Field(
        default_factory=list,
        description="Lista dos principais ensinamentos e pontos abordados na formação",
    )
    biblical_references: list[str] = Field(
        default_factory=list,
        description="Citações bíblicas, documentos da Igreja ou passagens do Catecismo mencionadas",
    )
    practical_application: str = Field(
        description="Aplicação prática ou compromisso semanal sugerido para os catequizandos"
    )
    full_summary: str = Field(
        description="Texto corrido consolidado resumindo a formação de forma didática"
    )


class SummaryGenerateRequest(BaseModel):
    lecture_id: int
    class_id: int
    theme: str
    date: str
    location: str = ""
    catequistas: list[str] = Field(default_factory=list)
    source_type: Literal["file", "manual"] = "manual"
    transcription: str


class SummaryDocumentResponse(BaseModel):
    id: str
    lecture_id: int
    class_id: int
    theme: str
    date: str
    location: str
    catequistas: list[str]
    source_type: str
    transcription: str
    summary: StructuredSummary
    created_at: str
    updated_at: str
