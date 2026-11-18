from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ai.marta_agent import ensure_openai_api_key, run_marta_chat, stream_marta_chat
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

    reply, tools_used = await run_marta_chat(payload)
    return MartaChatResponse(reply=reply, tools_used=tools_used)
