from fastapi.testclient import TestClient


def test_marta_chat_endpoint_returns_json_when_stream_false(monkeypatch):
    from routers import marta_router
    import server

    monkeypatch.setattr(marta_router, "ensure_openai_api_key", lambda: "sk-test")

    async def fake_run_marta_chat(payload):
        return "Olá! Posso ajudar com as turmas.", ["get_classes_overview"]

    monkeypatch.setattr(marta_router, "run_marta_chat", fake_run_marta_chat)

    client = TestClient(server.app)
    resp = client.post(
        "/api/v1/marta/chat",
        json={"message": "Quais turmas existem?", "stream": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Olá! Posso ajudar com as turmas."
    assert body["tools_used"] == ["get_classes_overview"]


def test_marta_chat_endpoint_returns_sse_when_stream_true(monkeypatch):
    from routers import marta_router
    import server

    monkeypatch.setattr(marta_router, "ensure_openai_api_key", lambda: "sk-test")

    async def fake_stream_marta_chat(payload):
        yield 'event: token\ndata: {"content": "Oi!"}\n\n'
        yield 'event: done\ndata: {"tools_used": []}\n\n'

    monkeypatch.setattr(marta_router, "stream_marta_chat", fake_stream_marta_chat)

    client = TestClient(server.app)
    resp = client.post(
        "/api/v1/marta/chat",
        json={"message": "Oi Marta", "stream": True},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert '"content": "Oi!"' in resp.text
