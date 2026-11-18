import json
from typing import Any
from langchain_core.tools import tool

from config.postgres import fetch_all


@tool
async def get_student_attendance(
    class_id: int | None = None,
    student_name: str | None = None,
    parish_id: int | None = None,
) -> str:
    """Consulta catequizandos (alunos), sacramentos (batismo e primeira comunhão), catequista responsável e contagem de presenças e faltas com justificativas."""
    conditions: list[str] = []
    params: dict[str, Any] = {}

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

    sql = f"""
        SELECT
            s."id",
            s."name",
            s."ClassId" AS class_id,
            c."type" AS class_type,
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
        GROUP BY s."id", s."name", s."ClassId", c."type", s."has_baptism", s."has_first_communion", u."name"
        ORDER BY absences_count DESC, s."name" ASC
        LIMIT 50
    """

    try:
        rows = await fetch_all(sql, params=params, limit=50)
        return json.dumps({"students": rows, "total": len(rows)}, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"Erro temporário ao consultar alunos e frequência no PostgreSQL: {exc}"
