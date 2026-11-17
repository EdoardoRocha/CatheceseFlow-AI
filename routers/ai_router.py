from datetime import datetime, timezone
import json
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from ai.agent import generate_lecture_summary
from config.database import get_summaries_collection
from helpers.pdf_generator import build_summary_pdf
from models.summary_model import SummaryDocumentResponse, SummaryGenerateRequest

router = APIRouter(prefix="/api/v1/summaries", tags=["Summaries"])


def _serialize_doc(doc: dict) -> SummaryDocumentResponse:
    return SummaryDocumentResponse(
        id=str(doc["_id"]),
        lecture_id=doc["lecture_id"],
        class_id=doc["class_id"],
        theme=doc["theme"],
        date=doc["date"],
        location=doc.get("location", ""),
        catequistas=doc.get("catequistas", []),
        source_type=doc.get("source_type", "manual"),
        transcription=doc.get("transcription", ""),
        summary=doc["summary"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


async def _generate_and_persist(payload: SummaryGenerateRequest) -> SummaryDocumentResponse:
    transcription = payload.transcription.strip()
    if len(transcription) < 10:
        raise HTTPException(
            status_code=400,
            detail="A transcrição da formação deve conter ao menos 10 caracteres.",
        )

    structured_summary = await generate_lecture_summary(
        theme=payload.theme,
        date=payload.date,
        transcription=transcription,
        catequistas=payload.catequistas,
    )

    collection = await get_summaries_collection()
    now_iso = datetime.now(timezone.utc).isoformat()
    existing = await collection.find_one({"lecture_id": payload.lecture_id})
    created_at = existing["created_at"] if existing else now_iso

    document_data = {
        "lecture_id": payload.lecture_id,
        "class_id": payload.class_id,
        "theme": payload.theme,
        "date": payload.date,
        "location": payload.location,
        "catequistas": payload.catequistas,
        "source_type": payload.source_type,
        "transcription": transcription,
        "summary": structured_summary.model_dump(),
        "created_at": created_at,
        "updated_at": now_iso,
    }

    await collection.update_one(
        {"lecture_id": payload.lecture_id},
        {"$set": document_data},
        upsert=True,
    )
    saved = await collection.find_one({"lecture_id": payload.lecture_id})
    return _serialize_doc(saved)


@router.post("/generate", response_model=SummaryDocumentResponse)
async def generate_summary(payload: SummaryGenerateRequest):
    return await _generate_and_persist(payload)


@router.post("/upload", response_model=SummaryDocumentResponse)
async def upload_and_generate_summary(
    file: UploadFile = File(...),
    lecture_id: int = Form(...),
    class_id: int = Form(...),
    theme: str = Form(...),
    date: str = Form(...),
    location: str = Form(""),
    catequistas: str = Form("[]"),
):
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo de texto com extensão .txt.",
        )

    raw_bytes = await file.read()
    try:
        transcription = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        transcription = raw_bytes.decode("latin-1", errors="replace")

    try:
        parsed_catequistas = json.loads(catequistas)
        if not isinstance(parsed_catequistas, list):
            parsed_catequistas = []
    except json.JSONDecodeError:
        parsed_catequistas = []

    payload = SummaryGenerateRequest(
        lecture_id=lecture_id,
        class_id=class_id,
        theme=theme,
        date=date,
        location=location,
        catequistas=[str(c) for c in parsed_catequistas],
        source_type="file",
        transcription=transcription,
    )
    return await _generate_and_persist(payload)


@router.get("/lecture/{lecture_id}", response_model=SummaryDocumentResponse)
async def get_summary_by_lecture(lecture_id: int):
    collection = await get_summaries_collection()
    doc = await collection.find_one({"lecture_id": lecture_id})
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Nenhum resumo encontrado para esta formação.",
        )
    return _serialize_doc(doc)


@router.get("/lecture/{lecture_id}/pdf")
async def download_summary_pdf(lecture_id: int):
    collection = await get_summaries_collection()
    doc = await collection.find_one({"lecture_id": lecture_id})
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Nenhum resumo encontrado para gerar o PDF.",
        )

    pdf_bytes = build_summary_pdf(doc)
    filename = f"resumo-formacao-{lecture_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
