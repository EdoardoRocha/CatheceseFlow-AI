import asyncio
import json
import pytest


def test_students_tool_returns_attendance_summary(monkeypatch):
    from tools import students_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["sql"] = sql
        captured["params"] = params
        captured["limit"] = limit
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
    assert data["order_by"] == "presences"
    assert data["limit"] == 50
    assert 'ORDER BY presences_count DESC, s."name" ASC' in captured["sql"]
    assert 's."birth_date"' in captured["sql"]
    assert 'EXTRACT(YEAR FROM AGE(%(ref_date)s::date, s."birth_date"))::INT AS age' in captured["sql"]
    assert "ref_date" in captured["params"]
    assert "LIMIT %(limit)s" in captured["sql"]
    assert captured["params"]["limit"] == 50
    assert captured["limit"] == 50


@pytest.mark.parametrize(
    ("order_by", "expected_clause"),
    [
        ("presences", 'ORDER BY presences_count DESC, s."name" ASC'),
        ("absences", 'ORDER BY absences_count DESC, s."name" ASC'),
        ("name", 'ORDER BY s."name" ASC'),
    ],
)
def test_students_tool_dynamic_ordering(monkeypatch, order_by, expected_clause):
    from tools import students_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(students_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(
        students_tool.get_student_attendance.ainvoke({"class_id": 4, "order_by": order_by})
    )
    data = json.loads(result)
    assert expected_clause in captured["sql"]
    assert data["order_by"] == order_by


@pytest.mark.parametrize(
    ("requested_limit", "expected_limit"),
    [
        (10, 10),
        (120, 120),
        (300, 150),
        (0, 1),
        (-5, 1),
    ],
)
def test_students_tool_limit_clamping(monkeypatch, requested_limit, expected_limit):
    from tools import students_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["params"] = params
        captured["limit"] = limit
        return []

    monkeypatch.setattr(students_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(
        students_tool.get_student_attendance.ainvoke({"limit": requested_limit})
    )
    data = json.loads(result)
    assert captured["params"]["limit"] == expected_limit
    assert captured["limit"] == expected_limit
    assert data["limit"] == expected_limit


def test_students_tool_handles_db_error_gracefully(monkeypatch):
    from tools import students_tool

    async def failing_fetch_all(sql, params=None, limit=50):
        raise RuntimeError("Conexão Postgres falhou")

    monkeypatch.setattr(students_tool, "fetch_all", failing_fetch_all)
    result = asyncio.run(students_tool.get_student_attendance.ainvoke({}))
    assert "Erro temporário ao consultar alunos e frequência no PostgreSQL" in result


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
