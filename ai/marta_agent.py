from collections.abc import AsyncIterator
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from ai.marta_prompt import build_marta_system_prompt
from models.marta_model import MartaChatRequest
from tools import MARTA_TOOLS, TOOLS_BY_NAME

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

MAX_ITERATIONS = 3


def ensure_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY não configurada no arquivo AI/.env.",
        )
    return api_key


def create_marta_llm() -> ChatOpenAI:
    api_key = ensure_openai_api_key()
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    return ChatOpenAI(model=model_name, api_key=api_key, temperature=0.2)


def _build_initial_messages(request: MartaChatRequest) -> list[BaseMessage]:
    messages: list[BaseMessage] = [
        SystemMessage(content=build_marta_system_prompt(request.context))
    ]
    for item in request.history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        else:
            messages.append(AIMessage(content=item.content))
    messages.append(HumanMessage(content=request.message))
    return messages


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts)
    return str(content or "")


async def _execute_tool_call(tool_call: dict) -> ToolMessage:
    name = str(tool_call.get("name", ""))
    args = tool_call.get("args") or {}
    call_id = str(tool_call.get("id") or name)
    tool_fn = TOOLS_BY_NAME.get(name)

    if tool_fn is None:
        output = f"Ferramenta '{name}' não encontrada."
    else:
        try:
            raw = await tool_fn.ainvoke(args)
            output = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        except Exception as exc:
            output = f"Erro ao executar ferramenta '{name}': {exc}"

    return ToolMessage(content=output, tool_call_id=call_id, name=name)


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def run_marta_chat(
    request: MartaChatRequest,
    llm: ChatOpenAI | None = None,
) -> tuple[str, list[str]]:
    """Executa o fluxo completo da martaAI em bloco único (JSON)."""
    model = llm or create_marta_llm()
    model_with_tools = model.bind_tools(MARTA_TOOLS)
    messages = _build_initial_messages(request)
    tools_used: list[str] = []

    for _ in range(MAX_ITERATIONS):
        ai_msg = await model_with_tools.ainvoke(messages)
        messages.append(ai_msg)

        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if not tool_calls:
            return _extract_text(ai_msg.content), tools_used

        for tc in tool_calls:
            tool_name = str(tc.get("name", ""))
            if tool_name and tool_name not in tools_used:
                tools_used.append(tool_name)
            messages.append(await _execute_tool_call(tc))

    # Síntese final sem novas ferramentas caso atinja MAX_ITERATIONS
    final_msg = await model.ainvoke(messages)
    return _extract_text(final_msg.content), tools_used


async def stream_marta_chat(
    request: MartaChatRequest,
    llm: ChatOpenAI | None = None,
) -> AsyncIterator[str]:
    """Executa o agente da martaAI emitindo eventos SSE (tool, token, done)."""
    model = llm or create_marta_llm()
    model_with_tools = model.bind_tools(MARTA_TOOLS)
    messages = _build_initial_messages(request)
    tools_used: list[str] = []

    try:
        for _ in range(MAX_ITERATIONS):
            accumulated = None
            async for chunk in model_with_tools.astream(messages):
                accumulated = chunk if accumulated is None else accumulated + chunk
                text_delta = _extract_text(getattr(chunk, "content", ""))
                has_tool_chunk = bool(getattr(chunk, "tool_call_chunks", None))
                if text_delta and not has_tool_chunk:
                    yield _format_sse("token", {"content": text_delta})

            if accumulated is None:
                break

            messages.append(accumulated)
            tool_calls = getattr(accumulated, "tool_calls", None) or []
            if not tool_calls:
                yield _format_sse("done", {"tools_used": tools_used})
                return

            for tc in tool_calls:
                tool_name = str(tc.get("name", ""))
                if tool_name and tool_name not in tools_used:
                    tools_used.append(tool_name)
                yield _format_sse("tool", {"tool": tool_name})
                messages.append(await _execute_tool_call(tc))

        # Limite atingido: gera resposta final em streaming sem ferramentas
        async for chunk in model.astream(messages):
            text_delta = _extract_text(getattr(chunk, "content", ""))
            if text_delta:
                yield _format_sse("token", {"content": text_delta})

        yield _format_sse("done", {"tools_used": tools_used})
    except Exception as exc:
        yield _format_sse("error", {"detail": str(exc)})
