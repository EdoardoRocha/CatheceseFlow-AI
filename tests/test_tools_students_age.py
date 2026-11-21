import asyncio
from datetime import date
import json
import pytest


def test_subtract_years_safe_handles_regular_and_leap_dates():
    from tools.students_age_tool import subtract_years_safe

    assert subtract_years_safe(date(2026, 11, 21), 15) == date(2011, 11, 21)
    assert subtract_years_safe(date(2024, 2, 29), 1) == date(2023, 2, 28)
    assert subtract_years_safe(date(2024, 2, 29), 4) == date(2020, 2, 29)


def test_age_range_to_birth_date_bounds():
    from tools.students_age_tool import age_range_to_birth_date_bounds

    ref = date(2026, 11, 21)

    assert age_range_to_birth_date_bounds(ref) == (None, None)
    assert age_range_to_birth_date_bounds(ref, min_age=15) == (None, date(2011, 11, 21))
    assert age_range_to_birth_date_bounds(ref, max_age=15) == (date(2010, 11, 21), None)
    assert age_range_to_birth_date_bounds(ref, min_age=14, max_age=16) == (
        date(2009, 11, 21),
        date(2012, 11, 21),
    )


def test_get_students_age_uses_sargable_bounds_and_returns_ages(monkeypatch):
    from tools import students_age_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["sql"] = sql
        captured["params"] = params
        captured["limit"] = limit
        return [
            {
                "id": 21,
                "name": "Lucas Gabriel",
                "class_id": 4,
                "class_type": "Crisma",
                "birth_date": "2010-05-12",
                "age": 16,
            },
            {
                "id": 22,
                "name": "Sem Data",
                "class_id": 4,
                "class_type": "Crisma",
                "birth_date": None,
                "age": None,
            },
        ]

    monkeypatch.setattr(students_age_tool, "get_brazil_today", lambda: date(2026, 11, 21))
    monkeypatch.setattr(students_age_tool, "fetch_all", fake_fetch_all)

    result = asyncio.run(
        students_age_tool.get_students_age.ainvoke(
            {"class_id": 4, "min_age": 15, "max_age": 17}
        )
    )
    data = json.loads(result)

    sql_where = captured["sql"].split("WHERE", 1)[1].split("ORDER BY", 1)[0]
    assert "AGE(" not in sql_where
    assert 's."birth_date" <= %(max_birth_date)s' in sql_where
    assert 's."birth_date" > %(min_birth_date_exclusive)s' in sql_where
    assert "EXTRACT(YEAR FROM AGE(%(ref_date)s::date, s.\"birth_date\"))::INT AS age" in captured["sql"]

    assert captured["params"]["ref_date"] == "2026-11-21"
    assert captured["params"]["max_birth_date"] == "2011-11-21"
    assert captured["params"]["min_birth_date_exclusive"] == "2008-11-21"

    assert data["total"] == 2
    assert data["reference_date"] == "2026-11-21"
    assert data["students"][0]["age"] == 16
    assert data["students"][1]["age"] is None


@pytest.mark.parametrize(
    ("order_by", "expected_clause"),
    [
        ("oldest", 'ORDER BY s."birth_date" ASC NULLS LAST, s."name" ASC'),
        ("youngest", 'ORDER BY s."birth_date" DESC NULLS LAST, s."name" ASC'),
        ("name", 'ORDER BY s."name" ASC'),
    ],
)
def test_get_students_age_ordering_clauses(monkeypatch, order_by, expected_clause):
    from tools import students_age_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["sql"] = sql
        return []

    monkeypatch.setattr(students_age_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(students_age_tool.get_students_age.ainvoke({"order_by": order_by}))
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
def test_get_students_age_limit_clamping(monkeypatch, requested_limit, expected_limit):
    from tools import students_age_tool

    captured: dict = {}

    async def fake_fetch_all(sql, params=None, limit=50):
        captured["params"] = params
        captured["limit"] = limit
        return []

    monkeypatch.setattr(students_age_tool, "fetch_all", fake_fetch_all)
    result = asyncio.run(students_age_tool.get_students_age.ainvoke({"limit": requested_limit}))
    data = json.loads(result)
    assert captured["params"]["limit"] == expected_limit
    assert captured["limit"] == expected_limit
    assert data["limit"] == expected_limit


def test_get_students_age_handles_db_error_and_is_registered(monkeypatch):
    from tools import MARTA_TOOLS, TOOLS_BY_NAME, students_age_tool

    assert "get_students_age" in TOOLS_BY_NAME
    assert any(t.name == "get_students_age" for t in MARTA_TOOLS)

    async def failing_fetch_all(sql, params=None, limit=50):
        raise RuntimeError("Falha de conexão")

    monkeypatch.setattr(students_age_tool, "fetch_all", failing_fetch_all)
    result = asyncio.run(students_age_tool.get_students_age.ainvoke({}))
    assert "Erro temporário ao consultar idades dos alunos no PostgreSQL" in result
