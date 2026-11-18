import json
import re
from typing import Any
from langchain_core.tools import tool

from config.database import get_summaries_collection


@tool
async def search_lecture_summaries(
    class_id: int | None = None,
    lecture_id: int | None = None,
    query: str | None = None,
) -> str:
    """Pesquisa resumos estruturados das formações já gerados pela IA e armazenados no MongoDB por turma, formação específica ou palavra-chave no tema/conteúdo."""
    mongo_filter: dict[str, Any] = {}

    if lecture_id is not None:
        mongo_filter["lecture_id"] = lecture_id
    if class_id is not None:
        mongo_filter["class_id"] = class_id
    if query and query.strip():
        escaped = re.escape(query.strip())
        regex = {"$regex": escaped, "$options": "i"}
        mongo_filter["$or"] = [
            {"theme": regex},
            {"summary.title": regex},
            {"summary.objective": regex},
            {"summary.full_summary": regex},
        ]

    try:
        collection = await get_summaries_collection()
        docs = await collection.find(mongo_filter).sort("date", -1).limit(10).to_list(length=10)
        summaries = [
            {
                "lecture_id": doc.get("lecture_id"),
                "class_id": doc.get("class_id"),
                "theme": doc.get("theme"),
                "date": doc.get("date"),
                "catequistas": doc.get("catequistas", []),
                "title": doc.get("summary", {}).get("title"),
                "objective": doc.get("summary", {}).get("objective"),
                "key_points": doc.get("summary", {}).get("key_points", []),
                "practical_application": doc.get("summary", {}).get("practical_application"),
            }
            for doc in docs
        ]
        return json.dumps(
            {"summaries": summaries, "total": len(summaries)},
            ensure_ascii=False,
        )
    except Exception as exc:
        return f"Erro temporário ao consultar resumos no MongoDB: {exc}"
