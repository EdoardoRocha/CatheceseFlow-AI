import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ai.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from models.summary_model import StructuredSummary

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


async def generate_lecture_summary(
    theme: str,
    date: str,
    transcription: str,
    catequistas: list[str] | None = None,
) -> StructuredSummary:
    """Gera um resumo estruturado da formação usando LangChain e OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY não configurada no arquivo AI/.env.",
        )

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=0.3)
    structured_llm = llm.with_structured_output(StructuredSummary)

    catequistas_text = ", ".join(catequistas) if catequistas else "Não informado"
    user_content = USER_PROMPT_TEMPLATE.format(
        theme=theme,
        date=date,
        catequistas=catequistas_text,
        transcription=transcription.strip(),
    )

    result = await structured_llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
    )
    return result
