from pathlib import Path
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from ai.marta_agent import ensure_openai_api_key, run_marta_chat, stream_marta_chat
from config.database import get_generated_formations_collection
from helpers.pdf_generator import build_formation_plan_pdf
from models.marta_model import MartaChatRequest, MartaChatResponse

router = APIRouter(prefix="/api/v1/marta", tags=["MartaAI"])


@router.post("/chat")
async def chat_with_marta(payload: MartaChatRequest):
    ensure_openai_api_key()

    if payload.stream:
        return StreamingResponse(
            stream_marta_chat(payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await run_marta_chat(payload)
    if len(result) == 3:
        reply, tools_used, attachments = result
    else:
        reply, tools_used = result
        attachments = []
    return MartaChatResponse(reply=reply, tools_used=tools_used, attachments=attachments)


@router.get("/pdfs/{pdf_id}")
async def download_generated_formation_pdf(pdf_id: str):
    if not ObjectId.is_valid(pdf_id):
        raise HTTPException(status_code=400, detail="Identificador de PDF inválido.")

    collection = await get_generated_formations_collection()
    doc = await collection.find_one({"_id": ObjectId(pdf_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="PDF de formação não encontrado.")

    pdf_bytes = build_formation_plan_pdf(doc)
    raw_name = str(doc.get("filename") or f"formacao-{pdf_id}.pdf")
    safe_filename = Path(raw_name).name.replace('"', "")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
        },
    )
