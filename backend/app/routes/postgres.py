from fastapi import APIRouter
from app.models.schemas import PgConnConfig, PgConnTestResult
import asyncpg

router = APIRouter()


async def _make_conn(cfg: PgConnConfig) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        user=cfg.username,
        password=cfg.password,
        ssl="require" if cfg.ssl else None,
        timeout=8,
    )


@router.post("/test", response_model=PgConnTestResult)
async def test_connection(cfg: PgConnConfig):
    try:
        conn = await _make_conn(cfg)
        await conn.close()
        return PgConnTestResult(ok=True)
    except Exception as e:
        return PgConnTestResult(ok=False, error=str(e))


@router.post("/tables", response_model=list)
async def list_tables(cfg: PgConnConfig):
    """
    Return all tables in the requested schema with real row counts.
    Uses schema-qualified relid lookup to avoid cross-schema ambiguity.
    """
    schema = cfg.schema_name or "public"
    try:
        conn = await _make_conn(cfg)

        rows = await conn.fetch(
            """
            SELECT
                t.table_name                                               AS name,
                pg_size_pretty(
                    pg_total_relation_size(
                        (quote_ident(t.table_schema) || '.' || quote_ident(t.table_name))::regclass
                    )
                )                                                          AS size,
                (
                    SELECT COUNT(*)
                    FROM   information_schema.columns c
                    WHERE  c.table_schema = t.table_schema
                    AND    c.table_name   = t.table_name
                )                                                          AS cols
            FROM   information_schema.tables t
            WHERE  t.table_schema = $1
            AND    t.table_type   = 'BASE TABLE'
            ORDER  BY t.table_name
            """,
            schema,
        )

        result = []
        for r in rows:
            # Schema-qualified relid — avoids picking the wrong table when two schemas
            # have tables with the same name (the original bug).
            cnt = await conn.fetchval(
                """
                SELECT reltuples::bigint
                FROM   pg_class   c
                JOIN   pg_namespace n ON n.oid = c.relnamespace
                WHERE  n.nspname = $1
                AND    c.relname = $2
                """,
                schema, r["name"]
            )
            label = f"{int(cnt):,}" if cnt and int(cnt) > 0 else "—"
            result.append({
                "name":  r["name"],
                "owner": cfg.username,
                "time":  "just now",
                "rows":  label,
                "cols":  int(r["cols"] or 0),
                "size":  r["size"] or "—",
            })

        await conn.close()
        return result
    except Exception as e:
        import logging
        logging.getLogger("aurum.postgres").error(f"list_tables error: {e}")
        return []


@router.post("/schemas", response_model=list)
async def list_schemas(cfg: PgConnConfig):
    """Return all non-system schema names in the database."""
    try:
        conn = await _make_conn(cfg)
        rows = await conn.fetch(
            """
            SELECT schema_name
            FROM   information_schema.schemata
            WHERE  schema_name NOT IN ('pg_catalog','information_schema','pg_toast')
            AND    schema_name NOT LIKE 'pg_temp_%'
            AND    schema_name NOT LIKE 'pg_toast_temp_%'
            ORDER  BY schema_name
            """
        )
        result = [r["schema_name"] for r in rows]
        await conn.close()
        return result
    except Exception as e:
        return []


@router.post("/tree", response_model=list)
async def schema_tree(cfg: PgConnConfig):
    """
    Return full schema tree: list of {schema, tables:[{name,cols}]}
    Used to populate the left-side tree in DatasetExplorerPage.
    """
    try:
        conn = await _make_conn(cfg)
        schemas = await conn.fetch(
            """
            SELECT schema_name
            FROM   information_schema.schemata
            WHERE  schema_name NOT IN ('pg_catalog','information_schema','pg_toast')
            AND    schema_name NOT LIKE 'pg_%'
            ORDER  BY schema_name
            """
        )
        tree = []
        for s in schemas:
            sname = s["schema_name"]
            tbls  = await conn.fetch(
                """
                SELECT table_name
                FROM   information_schema.tables
                WHERE  table_schema = $1 AND table_type = 'BASE TABLE'
                ORDER  BY table_name
                """,
                sname,
            )
            tree.append({
                "schema": sname,
                "tables": [t["table_name"] for t in tbls],
            })
        await conn.close()
        return tree
    except Exception as e:
        return []


@router.post("/schema", response_model=list)
async def get_table_schema(cfg: PgConnConfig, table: str):
    """Return column definitions for a specific table."""
    schema = cfg.schema_name or "public"
    try:
        conn = await _make_conn(cfg)
        rows = await conn.fetch(
            """
            SELECT column_name AS col, data_type AS type, is_nullable AS nullable
            FROM   information_schema.columns
            WHERE  table_schema = $1 AND table_name = $2
            ORDER  BY ordinal_position
            """,
            schema, table,
        )
        result = [dict(r) for r in rows]
        await conn.close()
        return result
    except Exception as e:
        return []
