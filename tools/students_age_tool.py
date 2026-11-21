from datetime import date, datetime
import json
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from config.postgres import MAX_QUERY_LIMIT, fetch_all

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")
MAX_STUDENTS_AGE_LIMIT = MAX_QUERY_LIMIT

_AGE_ORDER_BY_CLAUSES: dict[str, str] = {
    "oldest": 's."birth_date" ASC NULLS LAST, s."name" ASC',
    "youngest": 's."birth_date" DESC NULLS LAST, s."name" ASC',
    "name": 's."name" ASC',
}


def get_brazil_today() -> date:
    """Retorna a data atual no fuso oficial de Brasília (America/Sao_Paulo)."""
    return datetime.now(BRAZIL_TZ).date()


def subtract_years_safe(ref_date: date, years: int) -> date:
    """Subtrai anos preservando dia/mês e ajustando 29/02 para 28/02 em anos não bissextos."""
    target_year = ref_date.year - years
    try:
        return ref_date.replace(year=target_year)
    except ValueError:
        return date(target_year, 2, 28)


def age_range_to_birth_date_bounds(
    ref_date: date,
    min_age: int | None = None,
    max_age: int | None = None,
) -> tuple[date | None, date | None]:
    """Converte faixa etária em limites SARGable (exclusivo inferior, inclusivo superior) de birth_date."""
    max_birth_date_inclusive = (
        subtract_years_safe(ref_date, max(0, int(min_age))) if min_age is not None else None
    )
    min_birth_date_exclusive = (
        subtract_years_safe(ref_date, max(0, int(max_age)) + 1) if max_age is not None else None
    )
    return min_birth_date_exclusive, max_birth_date_inclusive


@tool
async def get_students_age(
    class_id: int | None = None,
    student_name: str | None = None,
    parish_id: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    order_by: Literal["oldest", "youngest", "name"] = "name",
    limit: int = 50,
) -> str:
    """Consulta a data de nascimento e calcula a idade exata dos catequizandos/crismandos no PostgreSQL.

    Use esta tool sempre que a pergunta envolver idade, faixa etária (`min_age`/`max_age`) ou ranking de mais velhos/mais novos:
    - Para filtrar alunos com idade mínima (ex.: 15 anos ou mais), passe `min_age=15`.
    - Para filtrar idade exata (ex.: 14 anos), passe `min_age=14` e `max_age=14`.
    - Para listar os mais velhos primeiro, passe `order_by="oldest"`; para os mais novos primeiro, `order_by="youngest"`.
    - Para ordem alfabética padrão, use `order_by="name"`.
    - Use `limit` (padrão 50, intervalo seguro de 1 a 150) para controlar quantos registros retornar.
    """
    ref_date = get_brazil_today()
    min_birth_date_exclusive, max_birth_date_inclusive = age_range_to_birth_date_bounds(
        ref_date,
        min_age=min_age,
        max_age=max_age,
    )

    conditions: list[str] = []
    params: dict[str, Any] = {
        "ref_date": ref_date.isoformat(),
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

    # Predicados SARGable na coluna bruta permitem uso de índice B-Tree sem scan completo
    if max_birth_date_inclusive is not None:
        conditions.append('s."birth_date" <= %(max_birth_date)s')
        params["max_birth_date"] = max_birth_date_inclusive.isoformat()

    if min_birth_date_exclusive is not None:
        conditions.append('s."birth_date" > %(min_birth_date_exclusive)s')
        params["min_birth_date_exclusive"] = min_birth_date_exclusive.isoformat()

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    safe_limit = max(1, min(int(limit), MAX_STUDENTS_AGE_LIMIT))
    order_clause = _AGE_ORDER_BY_CLAUSES.get(order_by, _AGE_ORDER_BY_CLAUSES["name"])
    params["limit"] = safe_limit

    sql = f"""
        SELECT
            s."id",
            s."name",
            s."ClassId" AS class_id,
            c."type" AS class_type,
            s."birth_date",
            EXTRACT(YEAR FROM AGE(%(ref_date)s::date, s."birth_date"))::INT AS age
        FROM "Students" s
        LEFT JOIN "Classes" c ON c."id" = s."ClassId"
        {where_clause}
        ORDER BY {order_clause}
        LIMIT %(limit)s
    """

    try:
        rows = await fetch_all(sql, params=params, limit=safe_limit)
        return json.dumps(
            {
                "students": rows,
                "total": len(rows),
                "reference_date": ref_date.isoformat(),
                "order_by": order_by,
                "limit": safe_limit,
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:
        return f"Erro temporário ao consultar idades dos alunos no PostgreSQL: {exc}"
