import asyncio
import json

from bson import ObjectId
from fastapi.testclient import TestClient


def test_build_formation_plan_pdf_generates_valid_pdf_bytes():
    from helpers.pdf_generator import build_formation_plan_pdf

    pdf_bytes = build_formation_plan_pdf(
        {
            "title": "Encontro sobre a Eucaristia — Memória e Partilha",
            "theme": "Eucaristia",
            "target_audience": "Primeira Comunhão",
            "duration_minutes": 90,
            "created_by": "Edoardo",
            "objective": "Conduzir as crianças à compreensão do sentido da Missa.",
            "opening_prayer": "Senhor Jesus, pão vivo descido do céu, abençoai nosso encontro.",
            "biblical_references": ["Jo 6,35-51", "1Cor 11,23-26"],
            "development_sections": [
                {
                    "title": "Acolhida e Contextualização",
                    "duration_minutes": 15,
                    "content": "Roda de conversa sobre refeições em família e gratidão.",
                },
                {
                    "title": "Palavra e Catecismo",
                    "duration_minutes": 35,
                    "content": "Leitura partilhada da Última Ceia e explicação dos sinais.",
                },
            ],
            "activity_or_dynamic": "Dinâmica da partilha dos pães em grupos.",
            "reflection_questions": ["O que você mais valoriza na Missa dominical?"],
            "closing_prayer": "Pai Nosso cantado em círculo.",
            "rag_sources_used": ["Formacao_Eucaristia_2025.pdf (p. 3)"],
        }
    )

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_generate_formation_pdf_tool_and_download_route(monkeypatch):
    from routers import marta_router
    import server
    from tools import MARTA_TOOLS, TOOLS_BY_NAME, formation_pdf_tool

    assert "generate_formation_pdf" in TOOLS_BY_NAME
    assert "search_formation_knowledge" in TOOLS_BY_NAME
    assert len(MARTA_TOOLS) >= 7

    stored: dict[str, dict] = {}

    class FakeInsertResult:
        def __init__(self, inserted_id):
            self.inserted_id = inserted_id

    class FakeCollection:
        async def insert_one(self, doc):
            oid = ObjectId()
            stored[str(oid)] = {"_id": oid, **doc}
            return FakeInsertResult(oid)

        async def find_one(self, query):
            oid = query.get("_id")
            return stored.get(str(oid))

    fake_col = FakeCollection()

    async def fake_get_col():
        return fake_col

    monkeypatch.setattr(formation_pdf_tool, "get_generated_formations_collection", fake_get_col)
    monkeypatch.setattr(marta_router, "get_generated_formations_collection", fake_get_col)

    raw_res = asyncio.run(
        formation_pdf_tool.generate_formation_pdf.ainvoke(
            {
                "title": "Formação de Pentecostes",
                "theme": "Dons do Espírito Santo",
                "objective": "Despertar os crismandos para a ação do Espírito.",
                "development_sections": [
                    {
                        "title": "Os Sete Dons",
                        "duration_minutes": 30,
                        "content": "Apresentação prática dos 7 dons aplicados à vida jovem.",
                    }
                ],
                "parish_id": 1,
                "class_id": 4,
            }
        )
    )
    payload = json.loads(raw_res)
    assert payload["status"] == "generated"
    pdf_id = payload["pdf_id"]
    assert payload["attachment"]["download_path"] == f"/marta/pdfs/{pdf_id}"
    assert payload["attachment"]["filename"] == "formacao-formacao-de-pentecostes.pdf"

    client = TestClient(server.app)

    dl_resp = client.get(f"/api/v1/marta/pdfs/{pdf_id}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert dl_resp.content.startswith(b"%PDF-")

    assert client.get("/api/v1/marta/pdfs/id-invalido").status_code == 400
    assert client.get(f"/api/v1/marta/pdfs/{ObjectId()}").status_code == 404
