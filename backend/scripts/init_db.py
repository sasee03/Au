"""
AURUM Database Initialisation Script
=====================================
Run ONCE before starting the backend:
    python scripts/init_db.py [--host localhost] [--port 5432]
                               [--user postgres] [--password yourpassword]
                               [--db aurum]

Architecture: ONE database, THREE schemas
─────────────────────────────────────────
  aurum  (single PostgreSQL database)
    ├── bronze.*   raw ingested data (no modifications)
    ├── silver.*   cleaned / transformed data
    ├── gold.*     KPI / analytics aggregation tables
    └── public.*   AURUM metadata (projects, runs, rules, kpis)

Why one DB not three?
  • CTEs can reference bronze → silver → gold in a single query
  • CREATE TABLE silver.x AS SELECT * FROM bronze.y works natively
  • No cross-database wrappers (postgres_fdw) needed
  • One connection pool, one set of credentials
"""
import asyncio
import argparse
import asyncpg


METADATA_DDL = """
-- ── Schemas ──────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- ── pgcrypto for gen_random_uuid() ───────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── AURUM metadata tables (stored in public schema) ───────────────────────────
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


async def main(host: str, port: int, user: str, password: str, db: str):
    print("\n=== AURUM Database Initialisation ===\n")

    # Step 1: create the database if it doesn't exist
    sys_conn = await asyncpg.connect(
        host=host, port=port, database="postgres", user=user, password=password
    )
    await sys_conn.execute("SET client_min_messages TO WARNING")

    exists = await sys_conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname=$1", db
    )
    if exists:
        print(f"  [skip]   database '{db}' already exists")
    else:
        await sys_conn.execute(f'CREATE DATABASE "{db}"')
        print(f"  [create] database '{db}' created ✓")

    await sys_conn.close()

    # Step 2: bootstrap schemas + metadata tables
    conn = await asyncpg.connect(
        host=host, port=port, database=db, user=user, password=password
    )
    await conn.execute(METADATA_DDL)
    await conn.close()

    print(f"\n  Schemas created inside '{db}':")
    print(f"    bronze.*  — raw ingested tables will appear here")
    print(f"    silver.*  — cleaned tables will appear here")
    print(f"    gold.*    — KPI / aggregation tables will appear here")
    print(f"    public.*  — AURUM metadata (projects, runs, rules, kpis)")

    print(f"\n✓ Database '{db}' is ready.\n")
    print("Update backend/.env:")
    print(f"  AURUM_DB_NAME={db}")
    print(f"  AURUM_DB_PASSWORD=<your password>\n")
    print("Then start the backend:")
    print("  uvicorn main:app --port 4000 --reload\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialise AURUM database")
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=5432)
    parser.add_argument("--user",     default="postgres")
    parser.add_argument("--password", default="postgres")
    parser.add_argument("--db",       default="aurum")
    args = parser.parse_args()
    asyncio.run(main(args.host, args.port, args.user, args.password, args.db))
