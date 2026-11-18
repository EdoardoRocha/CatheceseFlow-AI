import pytest


def test_build_postgres_dsn_prefers_database_url_when_not_development(monkeypatch):
    from config.postgres import resolve_postgres_dsn

    monkeypatch.setenv("POSTGRES_URI", "")
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@neon.tech/db?sslmode=require")

    dsn = resolve_postgres_dsn()
    assert dsn == "postgresql://user:pass@neon.tech/db?sslmode=require"


def test_build_postgres_dsn_uses_local_fields_in_development(monkeypatch):
    from config.postgres import resolve_postgres_dsn

    monkeypatch.setenv("POSTGRES_URI", "")
    monkeypatch.setenv("NODE_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql://should_not_use@prod/db")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "cathecese_dev")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "s@nha#1")

    dsn = resolve_postgres_dsn()
    assert dsn == "postgresql://postgres:s%40nha%231@localhost:5432/cathecese_dev"


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        'DELETE FROM "Students"',
        'UPDATE "Students" SET name = \'x\'',
        'INSERT INTO "Users" (name) VALUES (\'a\')',
        'DROP TABLE "Classes"',
        'SELECT * FROM "Classes"; DROP TABLE "Classes"',
    ],
)
def test_validate_read_only_sql_rejects_mutations(unsafe_sql):
    from config.postgres import validate_read_only_sql

    with pytest.raises(ValueError):
        validate_read_only_sql(unsafe_sql)


def test_validate_read_only_sql_allows_select_and_with():
    from config.postgres import validate_read_only_sql

    validate_read_only_sql('SELECT id, type FROM "Classes" WHERE id = %(id)s;')
    validate_read_only_sql('WITH base AS (SELECT id FROM "Students") SELECT * FROM base')
