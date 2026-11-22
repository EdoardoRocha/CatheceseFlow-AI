import asyncio
from langchain_core.messages import AIMessage, AIMessageChunk

from models.marta_model import MartaChatRequest, MartaPageContext


def test_build_marta_system_prompt_includes_active_context():
    from ai.marta_prompt import build_marta_system_prompt

    ctx = MartaPageContext(
        current_path="/classes/4",
        class_id=4,
        user_name="Edoardo",
        user_role="Coordenador",
        parish_id=1,
    )
    prompt = build_marta_system_prompt(ctx)
    assert "Marta" in prompt
    assert "</base_de_conhecimento_interna>" in prompt
    assert "search_formation_knowledge" in prompt
    assert "generate_formation_pdf" in prompt
    assert "class_id=4" in prompt
    assert "Edoardo" in prompt


def test_run_marta_chat_executes_tool_loop_and_caps_iterations():
    from ai import marta_agent

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "get_platform_faq",
                    "args": {"topic": "resumo pdf"},
                }
            ],
        ),
        AIMessage(content="Você pode gerar o resumo clicando em 'Gerar resumo'."),
    ]

    class FakeBoundLLM:
        async def ainvoke(self, messages):
            return responses.pop(0)

    class FakeLLM:
        def bind_tools(self, tools):
            return FakeBoundLLM()

        async def ainvoke(self, messages):
            return AIMessage(content="Resposta final")

    req = MartaChatRequest(
        message="Como gero um PDF?",
        context=MartaPageContext(current_path="/classes/4", class_id=4),
        stream=False,
    )
    reply, tools_used, attachments = asyncio.run(marta_agent.run_marta_chat(req, llm=FakeLLM()))
    assert "Gerar resumo" in reply
    assert tools_used == ["get_platform_faq"]
    assert attachments == []


def test_run_marta_chat_rag_and_pdf_generation_returns_attachment(monkeypatch):
    from bson import ObjectId
    from ai import marta_agent
    from tools import formation_pdf_tool, knowledge_tool

    async def fake_search_chunks(query, parish_id, category=None, top_k=5, embeddings=None):
        return (
            "cosine_fallback",
            [
                {
                    "document_title": "Roteiro Eucaristia 2025",
                    "category": "Crisma",
                    "page_number": 1,
                    "score": 0.92,
                    "content": "Modelo usado na paróquia: acolhida, oração, partilha.",
                }
            ],
        )

    class FakeInsertResult:
        inserted_id = ObjectId("507f1f77bcf86cd799439099")

    class FakeCol:
        async def insert_one(self, doc):
            return FakeInsertResult()

    async def fake_get_col():
        return FakeCol()

    monkeypatch.setattr(knowledge_tool, "search_knowledge_chunks", fake_search_chunks)
    monkeypatch.setattr(formation_pdf_tool, "get_generated_formations_collection", fake_get_col)

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_rag",
                    "name": "search_formation_knowledge",
                    "args": {"query": "Eucaristia", "parish_id": 1},
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_pdf",
                    "name": "generate_formation_pdf",
                    "args": {
                        "title": "Formação sobre Eucaristia",
                        "theme": "Eucaristia",
                        "objective": "Aprofundar o sentido da comunhão.",
                        "development_sections": [
                            {"title": "Palavra", "content": "Leitura de Jo 6."}
                        ],
                        "parish_id": 1,
                    },
                }
            ],
        ),
        AIMessage(content="Montei o roteiro usando a base anterior. Clique em Baixar PDF abaixo!"),
    ]

    class FakeBoundLLM:
        async def ainvoke(self, messages):
            return responses.pop(0)

    class FakeLLM:
        def bind_tools(self, tools):
            return FakeBoundLLM()

        async def ainvoke(self, messages):
            return AIMessage(content="Concluído")

    req = MartaChatRequest(
        message="Monte uma formação sobre Eucaristia e gere um PDF",
        context=MartaPageContext(current_path="/classes/4", class_id=4, parish_id=1),
        stream=False,
    )
    reply, tools_used, attachments = asyncio.run(marta_agent.run_marta_chat(req, llm=FakeLLM()))
    assert "Baixar PDF" in reply
    assert tools_used == ["search_formation_knowledge", "generate_formation_pdf"]
    assert len(attachments) == 1
    assert attachments[0]["id"] == "507f1f77bcf86cd799439099"
    assert attachments[0]["download_path"] == "/marta/pdfs/507f1f77bcf86cd799439099"


def test_stream_marta_chat_emits_tool_attachment_token_and_done_events(monkeypatch):
    from bson import ObjectId
    from ai import marta_agent
    from tools import formation_pdf_tool

    class FakeInsertResult:
        inserted_id = ObjectId("507f1f77bcf86cd799439088")

    class FakeCol:
        async def insert_one(self, doc):
            return FakeInsertResult()

    async def fake_get_col():
        return FakeCol()

    monkeypatch.setattr(formation_pdf_tool, "get_generated_formations_collection", fake_get_col)

    class FakeBoundLLM:
        def __init__(self):
            self.call = 0

        async def astream(self, messages):
            self.call += 1
            if self.call == 1:
                yield AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": "generate_formation_pdf",
                            "args": (
                                '{"title": "Formação Crisma", "theme": "Crisma", '
                                '"objective": "Confirmar na fé", '
                                '"development_sections": [{"title": "Parte 1", "content": "Conteudo"}]}'
                            ),
                            "id": "call_1",
                            "index": 0,
                        }
                    ],
                )
            else:
                yield AIMessageChunk(content="Pronto! ")
                yield AIMessageChunk(content="PDF gerado.")

    class FakeLLM:
        def bind_tools(self, tools):
            return FakeBoundLLM()

    async def collect():
        events = []
        async for ev in marta_agent.stream_marta_chat(
            MartaChatRequest(message="Gere o PDF"),
            llm=FakeLLM(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    joined = "".join(events)
    assert "event: tool" in joined
    assert "event: attachment" in joined
    assert "507f1f77bcf86cd799439088" in joined
    assert "event: token" in joined
    assert "Pronto! " in joined
    assert "event: done" in joined
