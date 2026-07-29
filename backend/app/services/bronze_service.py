"""
Bronze ingestion service.
Architecture: Single 'aurum' database, writes to bronze.* schema.
Naming convention (via naming.py):
- CSV upload  → bronze."{base_name}_bronze"   e.g. bronze."customer_orders_bronze"
- PostgreSQL  → bronze."{table}_bronze"        e.g. bronze."sales_bronze"
"""
import io
import asyncpg
import pandas as pd
import logging
from app.config import settings
from app.repositories import project_repository as repo

log = logging.getLogger("aurum.bronze")


def _pg_type(dtype: str) -> str:
    """
    Map a pandas dtype string to a PostgreSQL column type.
    Covers the full pandas → PostgreSQL type mapping.
    """
    d = str(dtype).lower()
    if d in ("int8", "int16", "int32"):                  return "INTEGER"
    if d in ("int64", "int_", "intp"):                   return "BIGINT"
    if d.startswith("int") or d.startswith("uint"):      return "BIGINT"
    if d in ("float16", "float32"):                      return "REAL"
    if d in ("float64", "float_"):                       return "DOUBLE PRECISION"
    if d.startswith("float"):                            return "DOUBLE PRECISION"
    if d in ("bool", "boolean"):                         return "BOOLEAN"
    if d.startswith("datetime64"):
        # timezone-aware: "datetime64[ns, utc]", "datetime64[ns, us/eastern]", etc.
        return "TIMESTAMP WITH TIME ZONE" if "," in d else "TIMESTAMP"
    if d.startswith("timedelta"):                        return "INTERVAL"
    if d == "category":                                  return "TEXT"
    if d in ("object", "string", "str"):                 return "TEXT"
    return "TEXT"   # safe fallback


async def _aurum_conn() -> asyncpg.Connection:
    """Connect to the single AURUM database (bronze/silver/gold schemas live here)."""
    return await asyncpg.connect(
        host=settings.AURUM_DB_HOST,
        port=settings.AURUM_DB_PORT,
        database=settings.AURUM_DB_NAME,
        user=settings.AURUM_DB_USER,
        password=settings.AURUM_DB_PASSWORD,
        timeout=15,
    )


async def _user_conn(pg_conn: dict) -> asyncpg.Connection:
    """Connect to the user-supplied PostgreSQL database."""
    return await asyncpg.connect(
        host=pg_conn.get("host", "localhost"),
        port=int(pg_conn.get("port", 5432)),
        database=pg_conn.get("database", ""),
        user=pg_conn.get("username") or pg_conn.get("user", "postgres"),
        password=pg_conn.get("password", ""),
        ssl="require" if pg_conn.get("ssl") else None,
        timeout=15,
    )


# ── CSV ingestion ─────────────────────────────────────────────────────────────

async def ingest_csv(
    file_bytes: bytes,
    dataset_name: str,
    delimiter: str = ",",
    encoding: str = "utf-8",
    project_id: str | None = None,
) -> dict:
    sep_map = {"Comma (,)": ",", "Tab (\\t)": "\t", "Semicolon (;)": ";", "Pipe (|)": "|"}
    sep = sep_map.get(delimiter, ",")

    # Read once with type inference to get the real dtypes
    df_typed = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=encoding)
    # Read again as all strings for safe storage (dirty data won't crash type conversion)
    df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=encoding, dtype=str)

    columns   = list(df.columns)
    row_count = len(df)
    # ── Naming convention: {base_name}_bronze ────────────────────────────────
    from app.services.naming import make_base_name, bronze_table as make_bronze_tbl
    base_name  = make_base_name(dataset_name)
    safe_name  = make_bronze_tbl(base_name)   # e.g. "customer_orders_bronze"
    bronze_tbl = f"bronze.{safe_name}"

    # Schema inference from df_typed (the one with real dtypes)
    schema_cols = [
        {"col": c, "type": _pg_type(str(df_typed[c].dtype)), "nullable": "YES"}
        for c in columns
    ]

    try:
        conn = await _aurum_conn()
        try:
            await conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")
            # Use the inferred types in CREATE TABLE (not TEXT everywhere)
            col_defs = ", ".join(f'"{c}" {schema_cols[i]["type"]}' for i, c in enumerate(columns))
            await conn.execute(f'DROP TABLE IF EXISTS bronze."{safe_name}"')
            await conn.execute(f'CREATE TABLE bronze."{safe_name}" ({col_defs})')
            # Build records from the string df for safe insertion
            # asyncpg copy_records needs Python-native types, not strings, for typed columns
            # Use executemany with explicit CAST to handle dirty values gracefully
            records = [
                tuple(v if pd.notna(v) else None for v in row)
                for row in df_typed.itertuples(index=False)
            ]
            try:
                await conn.copy_records_to_table(
                    safe_name, records=records, schema_name="bronze", columns=columns
                )
            except Exception:
                # Dirty data — fall back to TEXT-only table and re-insert as strings
                log.warning(f"[bronze] Type mismatch on insert — recreating as TEXT table")
                col_defs_text = ", ".join(f'"{c}" TEXT' for c in columns)
                await conn.execute(f'DROP TABLE IF EXISTS bronze."{safe_name}"')
                await conn.execute(f'CREATE TABLE bronze."{safe_name}" ({col_defs_text})')
                # Update schema_cols to reflect TEXT fallback
                for sc in schema_cols:
                    sc["type"] = "TEXT"
                str_records = [
                    tuple(str(v) if v is not None and pd.notna(v) else None for v in row)
                    for row in df.itertuples(index=False)
                ]
                await conn.copy_records_to_table(
                    safe_name, records=str_records, schema_name="bronze", columns=columns
                )
            log.info(f"[bronze] CSV written → bronze.\"{safe_name}\" ({row_count} rows)")
        finally:
            await conn.close()
    except Exception as e:
        log.warning(f"[bronze] CSV DB write skipped: {e}")

    if project_id:
        await repo.save_run(project_id, "csv", "bronze", "PASS", row_count, row_count,
                            {"table": bronze_tbl, "base_name": base_name, "columns": columns})

    sample = df.head(50).where(pd.notna(df.head(50)), None).to_dict(orient="records")
    return {
        "bronze_table": bronze_tbl,   # "bronze.customer_orders_bronze"
        "base_name":    base_name,    # "customer_orders"  ← stored in sessionStorage
        "row_count":    row_count,
        "col_count":    len(columns),
        "columns":      columns,
        "schema_cols":  schema_cols,
        "sample_rows":  sample,
    }


# ── PostgreSQL ingestion ──────────────────────────────────────────────────────

async def ingest_postgres(
    pg_conn: dict,
    tables: list[str],
    project_id: str | None = None,
) -> list[dict]:
    """
    Copy each source table into bronze schema.
    Writes into the AURUM database (not the user's DB) so all three layers
    are co-located for CTE access.
    """
    src_conn  = await _user_conn(pg_conn)
    aurum     = await _aurum_conn()
    src_schema = pg_conn.get("schema_name") or pg_conn.get("schema") or "public"
    results = []

    await aurum.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    for table in tables:
        try:
            # Schema from source
            col_rows = await src_conn.fetch(
                """SELECT column_name AS col, data_type AS type, is_nullable AS nullable
                   FROM information_schema.columns
                   WHERE table_schema=$1 AND table_name=$2
                   ORDER BY ordinal_position""",
                src_schema, table,
            )
            src_cols = [r["col"] for r in col_rows]
            schema_cols = [
                {"col": r["col"], "type": r["type"].upper(), "nullable": r["nullable"]}
                for r in col_rows
            ]

            cnt = await src_conn.fetchval(f'SELECT COUNT(*) FROM "{src_schema}"."{table}"')
            row_count = int(cnt or 0)

            # Fetch all rows from source
            rows = await src_conn.fetch(f'SELECT * FROM "{src_schema}"."{table}"')

            bronze_name = f"{table}_bronze"   # convention: {base_name}_bronze

            # Create bronze table in AURUM DB with TEXT types (safe for all sources)
            col_defs = ", ".join(f'"{c}" TEXT' for c in src_cols)
            await aurum.execute(f'DROP TABLE IF EXISTS bronze."{bronze_name}"')
            await aurum.execute(f'CREATE TABLE bronze."{bronze_name}" ({col_defs})')

            # Bulk insert
            records = [
                tuple(str(r[c]) if r[c] is not None else None for c in src_cols)
                for r in rows
            ]
            if records:
                await aurum.copy_records_to_table(
                    bronze_name, records=records, schema_name="bronze", columns=src_cols
                )
            log.info(f"[bronze] Created bronze.\"{bronze_name}\" ({row_count} rows)")

            if project_id:
                await repo.save_run(project_id, "postgres", "bronze", "PASS",
                                    row_count, row_count,
                                    {"table": bronze_name, "source": f"{src_schema}.{table}"})

            sample = [dict(r) for r in rows[:50]]

            results.append({
                "source_name": table,
                "bronze_name": bronze_name,
                "base_name":   table,          # base_name == source table name for postgres
                "row_count": row_count, "col_count": len(schema_cols),
                "schema_cols": schema_cols, "sample_rows": sample, "error": None,
            })

        except Exception as e:
            log.error(f"[bronze] Failed to ingest {table}: {e}")
            results.append({"source_name": table, "bronze_name": f"{table}_bronze",
                             "row_count": 0, "col_count": 0,
                             "schema_cols": [], "sample_rows": [], "error": str(e)})

    await src_conn.close()
    await aurum.close()
    return results


# ── Preview ───────────────────────────────────────────────────────────────────

async def list_bronze_tables() -> list:
    """Return all table names in the bronze schema."""
    try:
        conn = await _aurum_conn()
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='bronze' ORDER BY table_name"
        )
        result = [r["table_name"] for r in rows]
        await conn.close()
        return result
    except Exception as e:
        log.warning(f"[bronze] list_bronze_tables failed: {e}")
        return []


async def get_bronze_preview(table_name: str, pg_conn: dict | None = None) -> dict:
    """
    Return rows + schema for the specified bronze table.
    Matches by exact safe name — no fallback to arbitrary first table.
    """
    import re
    # Normalise to the same safe_name used at upload time
    bare = table_name.split(".")[-1]           # strip schema prefix if any
    bare = bare.replace("_bronze", "")          # strip _bronze suffix
    bare = re.sub(r"[^a-z0-9_]", "_", bare.lower())

    try:
        conn = await _aurum_conn()

        # Check exact match first, then try with/without common suffixes
        candidates_to_try = [bare, f"{bare}_bronze"]
        matched = None
        for candidate in candidates_to_try:
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='bronze' AND table_name=$1",
                candidate
            )
            if exists:
                matched = candidate
                break

        if not matched:
            # Partial match — only if exactly one result to avoid ambiguity
            all_bronze = await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='bronze'"
            )
            partials = [r["table_name"] for r in all_bronze if bare in r["table_name"]]
            if len(partials) == 1:
                matched = partials[0]
            elif len(partials) > 1:
                # Return list of available tables so frontend can show a picker
                await conn.close()
                return {
                    "rows": [], "schema_cols": [], "row_count": 0, "col_count": 0,
                    "available_tables": partials,
                    "error": f"Multiple bronze tables match '{bare}': {partials}"
                }

        if not matched:
            await conn.close()
            return {"rows": [], "schema_cols": [], "row_count": 0, "col_count": 0,
                    "error": f"No bronze table found for '{bare}'"}

        rows     = await conn.fetch(f'SELECT * FROM bronze."{matched}" LIMIT 50')
        col_rows = await conn.fetch(
            """SELECT column_name AS col, data_type AS type, is_nullable AS nullable
               FROM information_schema.columns
               WHERE table_schema='bronze' AND table_name=$1
               ORDER BY ordinal_position""",
            matched
        )
        cnt = await conn.fetchval(f'SELECT COUNT(*) FROM bronze."{matched}"')
        await conn.close()

        data = [dict(r) for r in rows]
        schema_cols = [
            {"col": r["col"], "type": r["type"].upper(), "nullable": r["nullable"],
             "meta": r["col"] in ("ingested_at", "source_file")}
            for r in col_rows
        ]
        return {
            "rows":         data,
            "schema_cols":  schema_cols,
            "row_count":    int(cnt or 0),
            "col_count":    len(schema_cols),
            "bronze_table": f"bronze.{matched}",
        }
    except Exception as e:
        log.warning(f"[bronze] preview failed: {e}")
        return {"rows": [], "schema_cols": [], "row_count": 0, "col_count": 0}
