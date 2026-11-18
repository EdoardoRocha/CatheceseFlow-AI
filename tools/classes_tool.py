import json
from typing import Any
from langchain_core.tools import tool

from config.postgres import fetch_all


@tool
async def get_classes_overview(
    class_id: int | None = None,
    parish_id: int | None = None,
) -> str:
    """Consulta as turmas de catequese no PostgreSQL (tipo, local, dia, horário, total de alunos, formações e catequistas responsáveis)."""
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if class_id is not None:
        conditions.append('c."id" = %(class_id)s')
        params["class_id"] = class_id

    if parish_id is not None:
        conditions.append('c."ParishId" = %(parish_id)s')
        params["parish_id"] = parish_id

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT
            c."id",
            c."type",
            c."location",
            c."day",
            CAST(c."start" AS TEXT) AS start,
            CAST(c."end" AS TEXT) AS "end",
            c."ParishId" AS parish_id,
            COUNT(DISTINCT s."id") AS total_students,
            COUNT(DISTINCT l."id") AS total_lectures,
            COALESCE(
                STRING_AGG(DISTINCT u."name", ', ') FILTER (WHERE u."name" IS NOT NULL),
                ''
            ) AS catequistas
        FROM "Classes" c
        LEFT JOIN "Students" s ON s."ClassId" = c."id"
        LEFT JOIN "Lectures" l ON l."ClassId" = c."id"
        LEFT JOIN "Users" u ON u."id" = s."UserId"
        {where_clause}
        GROUP BY c."id", c."type", c."location", c."day", c."start", c."end", c."ParishId"
        ORDER BY c."id" ASC
        LIMIT 50
    """

    try:
        rows = await fetch_all(sql, params=params, limit=50)
        return json.dumps({"classes": rows, "total": len(rows)}, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"Erro temporário ao consultar turmas no PostgreSQL: {exc}"
