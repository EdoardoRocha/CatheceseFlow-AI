import asyncio
from langchain_core.messages import AIMessage, AIMessageChunk


def test_build_marta_system_prompt_includes_active_context():
    from ai.marta_prompt import build_marta_system_prompt
    from models.marta_model import MartaPageContext

    ctx = MartaPageContext(
        current_path="/classes/4",
        class_id=4,
        user_name="Edoardo",
        user_role="Coordenador",
        parish_id=1,
    )
    prompt = build_marta_system_prompt(ctx)
    assert "martaAI" in prompt
    assert "class_id=4" in prompt
    assert "Edoardo" in prompt


def test_run_marta_chat_executes_tool_loop_and_caps_iterations(monkeypatch):
    from ai import marta_agent
    from models.marta_model import MartaChatRequest, MartaPageContext

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
    reply, tools_used = asyncio.run(marta_agent.run_marta_chat(req, llm=FakeLLM()))
    assert "Gerar resumo" in reply
    assert tools_used == ["get_platform_faq"]


def test_stream_marta_chat_emits_tool_token_and_done_events():
    from ai import marta_agent
    from models.marta_model import MartaChatRequest

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
                            "name": "get_platform_faq",
                            "args": '{"topic": "turma"}',
                            "id": "call_1",
                            "index": 0,
                        }
                    ],
                )
            else:
                yield AIMessageChunk(content="Clique ")
                yield AIMessageChunk(content="em Nova turma.")

    class FakeLLM:
        def bind_tools(self, tools):
            return FakeBoundLLM()

    async def collect():
        events = []
        async for ev in marta_agent.stream_marta_chat(
            MartaChatRequest(message="Como crio turma?"),
            llm=FakeLLM(),
        ):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    joined = "".join(events)
    assert "event: tool" in joined
    assert "event: token" in joined
    assert "Clique " in joined
    assert "event: done" in joined
