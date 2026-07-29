"""
AURUM single-database pool.
One database 'aurum', three schemas:
  bronze.*  – raw ingested tables
  silver.*  – cleaned/transformed tables
  gold.*    – KPI aggregation tables
  public.*  – AURUM metadata (projects, runs, rules, kpis)
"""
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_db() first")
    return _pool


async def init_db():
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            host=settings.AURUM_DB_HOST,
            port=settings.AURUM_DB_PORT,
            database=settings.AURUM_DB_NAME,
            user=settings.AURUM_DB_USER,
            password=settings.AURUM_DB_PASSWORD,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
        await _bootstrap_schema()
        print(f"[AURUM DB] Connected to '{settings.AURUM_DB_NAME}' — bronze/silver/gold schemas ready.")
    except Exception as e:
        print(f"[AURUM DB] Could not connect: {e}  — running without metadata persistence.")
        _pool = None


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _bootstrap_schema():
    """Bootstrap all schemas and metadata tables in a single transaction-safe block."""
    ddl = """
    -- Layer schemas
    CREATE SCHEMA IF NOT EXISTS bronze;
    CREATE SCHEMA IF NOT EXISTS silver;
    CREATE SCHEMA IF NOT EXISTS gold;

    -- UUID support
    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    -- AURUM metadata tables (public schema)
    CREATE TABLE IF NOT EXISTS projects (
        project_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        name        TEXT        NOT NULL,
        domain      TEXT        DEFAULT 'Other',
        description TEXT        DEFAULT '',
        environment TEXT        DEFAULT 'Development',
        status      TEXT        DEFAULT 'PASS',
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id  UUID        REFERENCES projects(project_id) ON DELETE CASCADE,
        source      TEXT,
        stage       TEXT,
        status      TEXT        DEFAULT 'running',
        rows_in     INTEGER     DEFAULT 0,
        rows_out    INTEGER     DEFAULT 0,
        details     JSONB       DEFAULT '{}',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS cleaning_rules (
        rule_id       UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id    UUID    REFERENCES projects(project_id) ON DELETE CASCADE,
        table_name    TEXT,
        rule_text     TEXT,
        generated_sql TEXT,
        rule_order    INTEGER DEFAULT 0,
        created_at    TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS gold_kpis (
        kpi_id      UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id  UUID    REFERENCES projects(project_id) ON DELETE CASCADE,
        requirement TEXT,
        kpi_name    TEXT,
        kpi_sql     TEXT,
        status      TEXT    DEFAULT 'Ready',
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(ddl)


async def execute(query: str, *args):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)
    except Exception:
        return None


async def fetch(query: str, *args) -> list:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
    except Exception:
        return []


async def fetchrow(query: str, *args):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    except Exception:
        return None
