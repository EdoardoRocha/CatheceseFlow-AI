import asyncio
import json


def test_faq_tool_returns_guidance_for_summary_and_unknown_topics():
    from tools.faq_tool import get_platform_faq

    res_pdf = get_platform_faq.invoke({"topic": "como gerar resumo pdf"})
    assert "Gerar resumo" in res_pdf or "PDF" in res_pdf

    res_unknown = get_platform_faq.invoke({"topic": "assunto aleatorio"})
    assert "Turmas" in res_unknown


def test_classes_tool_returns_formatted_classes(monkeypatch):
    from tools import classes_tool

    async def fake_fetch_all(sql, params=None, limit=50):
        return [
            {
                "id": 4,
                "type": "Crisma",
                "location": "Sala São Paulo",
                "day": "Sabado",
                "start": "09:00:00",
                "end": "10:30:00",
                "total_students": 18,
                "total_lectures": 5,
                "catequistas": "Ana Maria, João Pedro",
            }
        ]

    monkeypatch.setattr(classes_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(classes_tool.get_classes_overview.ainvoke({"class_id": 4}))
    data = json.loads(result)
    assert len(data["classes"]) == 1
    assert data["classes"][0]["type"] == "Crisma"
    assert data["classes"][0]["total_students"] == 18


def test_classes_tool_handles_db_error_gracefully(monkeypatch):
    from tools import classes_tool

    async def failing_fetch_all(sql, params=None, limit=50):
        raise RuntimeError("Conexão recusada")

    monkeypatch.setattr(classes_tool, "fetch_all", failing_fetch_all)
    result = asyncio.run(classes_tool.get_classes_overview.ainvoke({}))
    assert "Erro temporário ao consultar turmas" in result
