import asyncio
import json


def test_students_tool_returns_attendance_summary(monkeypatch):
    from tools import students_tool

    async def fake_fetch_all(sql, params=None, limit=50):
        return [
            {
                "id": 10,
                "name": "Maria Clara",
                "class_id": 4,
                "class_type": "Crisma",
                "has_baptism": True,
                "has_first_communion": True,
                "catequista_name": "Ana",
                "presences_count": 4,
                "absences_count": 2,
                "absence_reasons": "Viagem, Doença",
            }
        ]

    monkeypatch.setattr(students_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(
        students_tool.get_student_attendance.ainvoke({"class_id": 4, "student_name": "Maria"})
    )
    data = json.loads(result)
    assert len(data["students"]) == 1
    assert data["students"][0]["absences_count"] == 2
    assert "Viagem" in data["students"][0]["absence_reasons"]


def test_summaries_tool_queries_mongodb_and_handles_failure(monkeypatch):
    from tools import summaries_tool

    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        def sort(self, field, direction):
            return self

        def limit(self, n):
            return self

        async def to_list(self, length=10):
            return self._docs

    class FakeCollection:
        def find(self, mongo_filter):
            return FakeCursor(
                [
                    {
                        "lecture_id": 7,
                        "class_id": 4,
                        "theme": "Eucaristia e Partilha",
                        "date": "2026-11-10",
                        "catequistas": ["Ana"],
                        "summary": {
                            "title": "Sacramento da Eucaristia",
                            "objective": "Compreender o sentido da missa",
                            "key_points": ["Instituição na Última Ceia"],
                            "practical_application": "Participar da missa dominical",
                        },
                    }
                ]
            )

    async def fake_get_collection():
        return FakeCollection()

    monkeypatch.setattr(summaries_tool, "get_summaries_collection", fake_get_collection)
    res = asyncio.run(
        summaries_tool.search_lecture_summaries.ainvoke({"class_id": 4, "query": "Eucaristia"})
    )
    payload = json.loads(res)
    assert payload["total"] == 1
    assert payload["summaries"][0]["theme"] == "Eucaristia e Partilha"

    async def failing_get_collection():
        raise RuntimeError("SSL handshake failed")

    monkeypatch.setattr(summaries_tool, "get_summaries_collection", failing_get_collection)
    err_res = asyncio.run(summaries_tool.search_lecture_summaries.ainvoke({"class_id": 4}))
    assert "Erro temporário ao consultar resumos no MongoDB" in err_res
