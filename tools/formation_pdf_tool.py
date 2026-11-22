from datetime import datetime, timezone
import json
import re
import unicodedata
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config.database import get_generated_formations_collection


class FormationSectionInput(BaseModel):
    title: str = Field(..., min_length=1, description="Título do bloco/etapa da formação")
    content: str = Field(..., min_length=1, description="Explicação detalhada e orientações para o catequista")
    duration_minutes: int | None = Field(default=None, description="Tempo sugerido em minutos para este bloco")


def _slugify_filename(title: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    short_slug = slug[:48].strip("-") or "roteiro"
    return f"formacao-{short_slug}.pdf"


@tool
async def generate_formation_pdf(
    title: str,
    theme: str,
    objective: str,
    development_sections: list[FormationSectionInput],
    target_audience: str = "Catequizandos",
    duration_minutes: int | None = 60,
    opening_prayer: str = "",
    biblical_references: list[str] | None = None,
    activity_or_dynamic: str = "",
    reflection_questions: list[str] | None = None,
    closing_prayer: str = "",
    rag_sources_used: list[str] | None = None,
    parish_id: int | None = None,
    class_id: int | None = None,
    created_by: str = "",
) -> str:
    """Gera e salva um roteiro estruturado de formação no MongoDB para disponibilizar o download em PDF diretamente no chat.

    Use esta tool sempre que o usuário pedir para montar uma formação E gerar um arquivo PDF (ou pedir um PDF do roteiro elaborado).
    Após chamar esta tool, NÃO invente links externos: avise o usuário que o botão "Baixar PDF" já está disponível abaixo da sua resposta.
    """
    clean_title = title.strip() or theme.strip() or "Roteiro de Formação"
    filename = _slugify_filename(clean_title)
    now_iso = datetime.now(timezone.utc).isoformat()

    sections_payload = [
        sec.model_dump() if isinstance(sec, FormationSectionInput) else dict(sec)
        for sec in development_sections
    ]

    document_data = {
        "title": clean_title,
        "theme": theme.strip() or clean_title,
        "objective": objective.strip(),
        "target_audience": target_audience.strip() or "Catequizandos",
        "duration_minutes": duration_minutes,
        "opening_prayer": opening_prayer.strip(),
        "biblical_references": [str(r).strip() for r in (biblical_references or []) if str(r).strip()],
        "development_sections": sections_payload,
        "activity_or_dynamic": activity_or_dynamic.strip(),
        "reflection_questions": [str(q).strip() for q in (reflection_questions or []) if str(q).strip()],
        "closing_prayer": closing_prayer.strip(),
        "rag_sources_used": [str(s).strip() for s in (rag_sources_used or []) if str(s).strip()],
        "parish_id": parish_id,
        "class_id": class_id,
        "created_by": created_by.strip(),
        "filename": filename,
        "created_at": now_iso,
    }

    try:
        collection = await get_generated_formations_collection()
        insert_res = await collection.insert_one(document_data)
        pdf_id = str(insert_res.inserted_id)

        attachment = {
            "type": "pdf",
            "id": pdf_id,
            "title": clean_title,
            "filename": filename,
            "download_path": f"/marta/pdfs/{pdf_id}",
        }
        return json.dumps(
            {
                "status": "generated",
                "pdf_id": pdf_id,
                "attachment": attachment,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return f"Erro temporário ao gerar o PDF da formação no MongoDB: {exc}"
