import json
from typing import Any, Literal
from langchain_core.tools import tool

from config.postgres import MAX_QUERY_LIMIT, fetch_all
from tools.students_age_tool import get_brazil_today

MAX_STUDENTS_LIMIT = MAX_QUERY_LIMIT

_ORDER_BY_CLAUSES: dict[str, str] = {
    "presences": 'presences_count DESC, s."name" ASC',
    "absences": 'absences_count DESC, s."name" ASC',
    "name": 's."name" ASC',
}


@tool
async def get_student_attendance(
    class_id: int | None = None,
    student_name: str | None = None,
    parish_id: int | None = None,
    order_by: Literal["presences", "absences", "name"] = "presences",
    limit: int = 50,
) -> str:
    """Consulta catequizandos (alunos), data de nascimento e idade atual calculada (`birth_date` e `age`), sacramentos (batismo e primeira comunhão), catequista responsável e contagem de presenças e faltas com justificativas.

    Orientações:
    - Para perguntas focadas apenas em idade, faixa etária (`min_age`/`max_age`) ou ranking de mais velhos/novos, prefira a tool `get_students_age`.
    - Use `order_by="presences"` (padrão) para consultas sobre alunos mais presentes, ranking de assiduidade ou maior participação.
    - Use `order_by="absences"` para consultas sobre alunos mais faltosos ou com maior número de faltas.
    - Use `order_by="name"` para listagens gerais em ordem alfabética.
    - Use `limit` (padrão 50, intervalo seguro de 1 a 150) para controlar quantos alunos retornar.
    """
    conditions: list[str] = []
    params: dict[str, Any] = {
        "ref_date": get_brazil_today().isoformat(),
    }

    if class_id is not None:
        conditions.append('s."ClassId" = %(class_id)s')
        params["class_id"] = class_id

    if student_name and student_name.strip():
        conditions.append('s."name" ILIKE %(student_name)s')
        params["student_name"] = f"%{student_name.strip()}%"

    if parish_id is not None:
        conditions.append('c."ParishId" = %(parish_id)s')
        params["parish_id"] = parish_id

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    safe_limit = max(1, min(int(limit), MAX_STUDENTS_LIMIT))
    order_clause = _ORDER_BY_CLAUSES.get(order_by, _ORDER_BY_CLAUSES["presences"])
    params["limit"] = safe_limit

    sql = f"""
        SELECT
            s."id",
            s."name",
            s."ClassId" AS class_id,
            c."type" AS class_type,
            s."birth_date",
            EXTRACT(YEAR FROM AGE(%(ref_date)s::date, s."birth_date"))::INT AS age,
            s."has_baptism",
            s."has_first_communion",
            u."name" AS catequista_name,
            COUNT(DISTINCT att."id") AS presences_count,
            COUNT(DISTINCT absn."id") AS absences_count,
            COALESCE(
                STRING_AGG(DISTINCT absn."reason", ' | ') FILTER (WHERE absn."reason" IS NOT NULL),
                ''
            ) AS absence_reasons
        FROM "Students" s
        LEFT JOIN "Classes" c ON c."id" = s."ClassId"
        LEFT JOIN "Users" u ON u."id" = s."UserId"
        LEFT JOIN "Attendances" att ON att."StudentId" = s."id"
        LEFT JOIN "Absences" absn ON absn."StudentId" = s."id"
        {where_clause}
        GROUP BY s."id", s."name", s."ClassId", c."type", s."birth_date", s."has_baptism", s."has_first_communion", u."name"
        ORDER BY {order_clause}
        LIMIT %(limit)s
    """

    try:
        rows = await fetch_all(sql, params=params, limit=safe_limit)
        return json.dumps(
            {
                "students": rows,
                "total": len(rows),
                "order_by": order_by,
                "limit": safe_limit,
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        return f"Erro temporário ao consultar alunos e frequência no PostgreSQL: {exc}"
