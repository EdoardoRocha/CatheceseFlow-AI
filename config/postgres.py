import asyncio
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote_plus

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

_AI_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_BACKEND_ENV_PATH = Path(__file__).resolve().parent.parent.parent / "Backend" / ".env"

# Prioriza AI/.env e usa Backend/.env como fallback para variáveis Postgres
load_dotenv(_AI_ENV_PATH, override=False)
if _BACKEND_ENV_PATH.exists():
    load_dotenv(_BACKEND_ENV_PATH, override=False)

_FORBIDDEN_SQL_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXECUTE|CALL|MERGE|REPLACE)\b",
    re.IGNORECASE,
)


def resolve_postgres_dsn() -> str | None:
    """Resolve a URI de conexão do PostgreSQL respeitando o padrão do Backend."""
    explicit_uri = os.getenv("POSTGRES_URI", "").strip()
    if explicit_uri:
        return explicit_uri

    node_env = os.getenv("NODE_ENV", "").strip().lower()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url and node_env != "development":
        return database_url

    db_name = os.getenv("DB_NAME", "").strip()
    db_user = os.getenv("DB_USER", "").strip()
    if db_name and db_user:
        db_host = os.getenv("DB_HOST", "localhost").strip() or "localhost"
        db_port = os.getenv("DB_PORT", "5432").strip() or "5432"
        db_password = os.getenv("DB_PASSWORD", "")
        encoded_user = quote_plus(db_user)
        encoded_pass = quote_plus(db_password)
        return f"postgresql://{encoded_user}:{encoded_pass}@{db_host}:{db_port}/{db_name}"

    if database_url:
        return database_url

    return None


def validate_read_only_sql(sql: str) -> str:
    """Garante que apenas consultas SELECT/WITH em instrução única sejam executadas."""
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("A query SQL não pode estar vazia.")

    without_trailing_semicolon = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    if ";" in without_trailing_semicolon:
        raise ValueError("Múltiplas instruções SQL não são permitidas.")

    upper = without_trailing_semicolon.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("Apenas consultas SELECT ou WITH são permitidas para a martaAI.")

    if _FORBIDDEN_SQL_KEYWORDS.search(without_trailing_semicolon):
        raise ValueError("Instrução SQL contém comando de escrita ou DDL não permitido.")

    return without_trailing_semicolon


def _sync_fetch_all(
    sql: str,
    params: dict[str, Any] | tuple[Any, ...] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    safe_sql = validate_read_only_sql(sql)
    safe_limit = max(1, min(int(limit), 50))
    dsn = resolve_postgres_dsn()
    if not dsn:
        raise RuntimeError(
            "Configuração do PostgreSQL não encontrada (defina POSTGRES_URI, DATABASE_URL ou DB_* no AI/.env)."
        )

    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(safe_sql, params or {})
            return list(cur.fetchmany(safe_limit))


async def fetch_all(
    sql: str,
    params: dict[str, Any] | tuple[Any, ...] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Executa uma consulta SELECT somente-leitura no PostgreSQL sem bloquear o event loop."""
    return await asyncio.to_thread(_sync_fetch_all, sql, params, limit)
