"""
Bronze ingestion service.
Architecture: Single 'aurum' database, writes to bronze.* schema.
Naming convention (via naming.py):
- CSV upload  → bronze."{base_name}_bronze"   e.g. bronze."customer_orders_bronze"
- PostgreSQL  → bronze."{table}_bronze"        e.g. bronze."sales_bronze"
"""
import asyncio
import io
import asyncpg
import pandas as pd
import logging
import os
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4
from app.config import settings
from app.repositories import project_repository as repo
from app.services.dq_calculation import (
    DataQualityAccumulator,
    QUALITY_DIMENSIONS,
    check_severity,
    dimension_statuses,
)
from app.services.dq_engine_polars import calculate_data_quality_pl
from app.services import dq_engine_sql

log = logging.getLogger("aurum.bronze")
MIN_REAL_RUNS_FOR_TREND = 5
MAX_SYNC_DQ_ROWS = 2_000_000


class DQReportTooLargeError(RuntimeError):
    pass


DQ_BATCH_SIZE = 5000
INGEST_BATCH_SIZE = 5000


def _coerce_numeric_columns(frame: pd.DataFrame, numeric_names: set[str]) -> pd.DataFrame:
    for column in numeric_names:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


async def _calculate_table_quality(table_name: str, column_names: list[str]) -> dict:
    engine_name = dq_engine_sql.resolve_engine()
    if engine_name == "sql":
        pool = await dq_engine_sql.get_dq_pool()
        async with pool.acquire() as conn:
            metadata = await dq_engine_sql.table_metadata(conn, table_name)
            tier1 = await dq_engine_sql.run_tier1(conn, metadata)
            result = await dq_engine_sql.run_tier2(conn, tier1)
        checks = result["checks"]
        result.update({
            "score": round(
                sum(check["passed"] for check in checks) / len(checks) * 100, 2
            ) if checks else 0.0,
            "passed_checks": sum(check["passed"] for check in checks),
            "total_checks": len(checks),
            "issue_count": sum(not check["passed"] for check in checks),
            "issues": [check for check in checks if not check["passed"]],
        })
        return result
    pool = await database.get_pool()
    query = f'SELECT * FROM bronze."{table_name}"'
    numeric_columns = await database.fetch(
        """SELECT column_name
           FROM information_schema.columns
           WHERE table_schema='bronze' AND table_name=$1
             AND data_type IN ('numeric', 'integer', 'bigint', 'smallint',
                               'real', 'double precision')""",
        table_name,
    )
    numeric_names = {row["column_name"] for row in numeric_columns}
    log.info("Starting exact DQ scan for bronze.%s using %s in batches of %s", table_name, engine_name, DQ_BATCH_SIZE)
    frames: list[pd.DataFrame] = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            cursor = await conn.cursor(query)
            while True:
                records = await cursor.fetch(DQ_BATCH_SIZE, timeout=300)
                if not records:
                    break
                frame = pd.DataFrame([dict(record) for record in records], columns=column_names)
                _coerce_numeric_columns(frame, numeric_names)
                frames.append(frame)
            duplicate_row = await conn.fetchrow(
                f"""SELECT COUNT(*) - COUNT(DISTINCT to_jsonb(source_row)) AS duplicate_count
                    FROM bronze."{table_name}" AS source_row""",
                timeout=300,
            )
    duplicate_count = int(duplicate_row["duplicate_count"] or 0) if duplicate_row else 0
    if not frames:
        return {"table_name": table_name, "score": 0.0, "passed_checks": 0, "total_checks": 0, "issue_count": 0, "rows_tested": 0, "checks": [], "issues": []}
    combined = pd.concat(frames, ignore_index=True)
    if engine_name == "pandas":
        accumulator = DataQualityAccumulator(table_name, column_names)
        for frame in frames:
            await asyncio.to_thread(accumulator.update, frame)
        result = accumulator.finish(duplicate_count)
    else:
        result = await asyncio.to_thread(calculate_data_quality_pl, combined, table_name)
    log.info("Completed exact DQ scan for bronze.%s: %s rows, %s duplicate rows", table_name, len(combined), duplicate_count)
    return result


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


_DICTIONARY_PG_TYPES = {
    "TEXT": "TEXT",
    "NUMERIC": "NUMERIC",
    "BIGINT": "BIGINT",
    "DATE": "DATE",
}


def _dictionary_pg_type(type_name: str) -> str | None:
    """Return a safe PostgreSQL type for supported dictionary type names."""
    return _DICTIONARY_PG_TYPES.get(str(type_name).strip().upper())


def _source_pg_type(column: dict) -> str:
    """Map information_schema type metadata to a safe PostgreSQL type declaration."""
    data_type = str(column["data_type"]).lower()
    char_length = column.get("character_maximum_length")
    precision = column.get("numeric_precision")
    scale = column.get("numeric_scale")
    datetime_precision = column.get("datetime_precision")

    if data_type in ("character varying", "varchar"):
        return f"VARCHAR({int(char_length)})" if char_length else "VARCHAR"
    if data_type in ("character", "char"):
        return f"CHAR({int(char_length)})" if char_length else "CHAR"
    if data_type in ("numeric", "decimal"):
        return f"NUMERIC({int(precision)},{int(scale or 0)})" if precision else "NUMERIC"
    if data_type in ("smallint", "integer", "bigint", "real", "double precision",
                     "boolean", "date", "text", "bytea", "uuid", "json", "jsonb",
                     "interval"):
        return data_type.upper()
    if data_type in ("timestamp without time zone", "timestamp with time zone",
                     "time without time zone", "time with time zone"):
        base_type, zone = data_type.split(" ", 1)
        precision = f"({int(datetime_precision)})" if datetime_precision is not None else ""
        return f"{base_type.upper()}{precision} {zone.upper()}"

    if data_type == "array":
        array_element_types = {
            "_text": "TEXT",
            "_varchar": "VARCHAR",
            "_int2": "SMALLINT",
            "_int4": "INTEGER",
            "_int8": "BIGINT",
            "_numeric": "NUMERIC",
            "_date": "DATE",
            "_timestamp": "TIMESTAMP",
            "_timestamptz": "TIMESTAMP WITH TIME ZONE",
            "_bool": "BOOLEAN",
            "_uuid": "UUID",
        }
        element_type = array_element_types.get(str(column.get("udt_name", "")).lower())
        if element_type:
            return f"{element_type}[]"

    raise ValueError(
        f"Unsupported PostgreSQL source type {column['data_type']!r} "
        f"for column {column['column_name']!r}"
    )


def _normalize_column_name(name: str) -> str:
    return re.sub(r"\s+", "_", str(name).strip().lower())


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _redact_ingest_error(error: Exception, pg_conn: dict) -> str:
    message = str(error)
    for key in ("password", "dsn"):
        secret = pg_conn.get(key)
        if secret:
            message = message.replace(str(secret), "[REDACTED]")
    return re.sub(
        r"(?i)(postgres(?:ql)?://)[^@\s]+@",
        r"\1[REDACTED]@",
        message,
    )


async def _source_dictionary_rows(conn: asyncpg.Connection) -> list[dict] | None:
    dictionary_exists = await conn.fetchval(
        "SELECT to_regclass('metadata.data_dictionary') IS NOT NULL"
    )
    if not dictionary_exists:
        return None
    rows = await conn.fetch(
        """SELECT logical_table, physical_files, column_number, column_name, data_type
           FROM metadata.data_dictionary
           ORDER BY logical_table, column_number"""
    )
    return [dict(row) for row in rows]


def _dictionary_table_types(
    rows: list[dict] | None,
    table: str,
    filename: str | None = None,
) -> dict[str, str]:
    if not rows:
        return {}

    table_key = _normalize_column_name(table)
    filename_key = os.path.basename(filename or "").strip().lower()
    stem_key = _normalize_column_name(os.path.splitext(filename_key)[0]) if filename_key else ""
    matched_table = None
    for row in rows:
        logical_table = str(row["logical_table"])
        physical_files = str(row.get("physical_files") or "").strip()
        if _normalize_column_name(logical_table) in {table_key, stem_key}:
            matched_table = logical_table
            break
        if filename_key and physical_files.lower() == filename_key:
            matched_table = logical_table
            break

    if matched_table is None and filename_key and re.fullmatch(r"(.+\s-\s)?[a-z]\.csv", filename_key):
        partition_tables = {
            str(row["logical_table"])
            for row in rows
            if "partition" in str(row.get("physical_files") or "").lower()
        }
        if len(partition_tables) == 1:
            matched_table = next(iter(partition_tables))

    if matched_table is None:
        return {}
    return {
        _normalize_column_name(row["column_name"]): str(row["data_type"])
        for row in rows
        if str(row["logical_table"]) == matched_table
    }


def _csv_native_value(value, pg_type: str):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None

    normalized_type = pg_type.upper()
    if normalized_type == "TEXT":
        return str(value)
    if normalized_type.startswith("NUMERIC"):
        number = Decimal(str(value).strip())
        if not number.is_finite():
            raise ValueError("numeric value must be finite")
        return number
    if normalized_type == "BIGINT":
        number = Decimal(str(value).strip())
        if not number.is_finite() or number != number.to_integral_value():
            raise ValueError("value is not an integer")
        return int(number)
    if normalized_type == "DATE":
        parsed = pd.to_datetime(value, errors="coerce", format="mixed")
        if pd.isna(parsed):
            raise ValueError("value is not a valid date")
        return parsed.date()
    return value.item() if hasattr(value, "item") else value


def _csv_typed_columns(
    inferred: pd.DataFrame,
    raw: pd.DataFrame,
    dictionary_types: dict[str, str],
    table_name: str,
) -> tuple[list[dict], list[list]]:
    schema_cols = []
    typed_columns = []
    for column in inferred.columns:
        dictionary_type = dictionary_types.get(_normalize_column_name(column))
        if dictionary_type is not None:
            pg_type = _dictionary_pg_type(dictionary_type)
            if pg_type is None:
                raise ValueError(
                    f"Unsupported dictionary type {dictionary_type!r} for "
                    f"table {table_name}, column {column!r}"
                )
            source = raw[column]
        else:
            pg_type = _pg_type(str(inferred[column].dtype))
            source = inferred[column]

        converted = []
        invalid_values = []
        for value in source:
            try:
                converted.append(_csv_native_value(value, pg_type))
            except (InvalidOperation, TypeError, ValueError, OverflowError):
                converted.append(None)
                if len(invalid_values) < 5:
                    display_value = str(value)
                    invalid_values.append(display_value[:120])
        if invalid_values:
            raise ValueError(
                f"CSV ingest failed for table {table_name}, column {column!r} "
                f"({pg_type}); invalid values (up to 5): {invalid_values!r}"
            )

        schema_cols.append({"col": column, "type": pg_type, "nullable": "YES"})
        typed_columns.append(converted)
    return schema_cols, typed_columns


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
    dictionary_connection: dict | None = None,
    source_filename: str | None = None,
) -> dict:
    sep_map = {"Comma (,)": ",", "Tab (\\t)": "\t", "Semicolon (;)": ";", "Pipe (|)": "|"}
    sep = sep_map.get(delimiter, ",")

    df_typed = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=encoding)
    df_raw = pd.read_csv(
        io.BytesIO(file_bytes), sep=sep, encoding=encoding, dtype=str,
        keep_default_na=False,
    )

    columns = list(df_typed.columns)
    if list(df_raw.columns) != columns:
        raise ValueError("CSV headers changed while resolving column types")
    row_count = len(df_typed)
    # ── Naming convention: {base_name}_bronze ────────────────────────────────
    from app.services.naming import make_base_name, bronze_table as make_bronze_tbl
    base_name  = make_base_name(dataset_name)
    safe_name  = make_bronze_tbl(base_name)   # e.g. "customer_orders_bronze"
    bronze_tbl = f"bronze.{safe_name}"

    source_dictionary_types = {}
    source_connection = None
    try:
        if dictionary_connection:
            source_connection = await _user_conn(dictionary_connection)
            dictionary_rows = await _source_dictionary_rows(source_connection)
            source_dictionary_types = _dictionary_table_types(
                dictionary_rows, dataset_name, source_filename
            )
    finally:
        if source_connection:
            await source_connection.close()

    schema_cols, typed_columns = _csv_typed_columns(
        df_typed, df_raw, source_dictionary_types, bronze_tbl
    )
    col_defs = ", ".join(
        f'{_quote_identifier(column["col"])} {column["type"]}'
        for column in schema_cols
    )
    stage_name = f"_{safe_name[:38]}_{uuid4().hex[:16]}"

    conn = await _aurum_conn()
    try:
        async with conn.transaction():
            await conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")
            await conn.execute(
                f"CREATE TABLE bronze.{_quote_identifier(stage_name)} ({col_defs})"
            )
            for start in range(0, row_count, INGEST_BATCH_SIZE):
                end = min(start + INGEST_BATCH_SIZE, row_count)
                records = zip(*(column[start:end] for column in typed_columns))
                await conn.copy_records_to_table(
                    stage_name, records=records, schema_name="bronze", columns=columns
                )
            await conn.execute(f'DROP TABLE IF EXISTS bronze.{_quote_identifier(safe_name)}')
            await conn.execute(
                f"ALTER TABLE bronze.{_quote_identifier(stage_name)} "
                f"RENAME TO {_quote_identifier(safe_name)}"
            )
        log.info("[bronze] CSV written to bronze.%s (%s rows)", safe_name, row_count)
    except Exception as exc:
        raise RuntimeError(f"CSV ingest failed for table {bronze_tbl}: {exc}") from exc
    finally:
        await conn.close()

    if project_id:
        await repo.save_run(project_id, "csv", "bronze", "PASS", row_count, row_count,
                            {"table": bronze_tbl, "base_name": base_name, "columns": columns})

    sample_frame = df_raw.head(50).replace("", pd.NA)
    sample = sample_frame.astype(object).where(pd.notna(sample_frame), None).to_dict(orient="records")
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

    for table in tables:
        table_started = time.perf_counter()
        try:
            col_rows = await src_conn.fetch(
                """SELECT column_name, data_type, is_nullable,
                          character_maximum_length, numeric_precision, numeric_scale,
                          datetime_precision, udt_name
                   FROM information_schema.columns
                   WHERE table_schema=$1 AND table_name=$2
                   ORDER BY ordinal_position""",
                src_schema, table,
            )
            if not col_rows:
                raise ValueError(f"Source table {src_schema}.{table} was not found")

            dictionary_rows = await _source_dictionary_rows(src_conn)
            dictionary_types = _dictionary_table_types(dictionary_rows, table)
            source_columns = [dict(row) for row in col_rows]
            schema_cols = []
            for column in source_columns:
                dictionary_type = dictionary_types.get(
                    _normalize_column_name(column["column_name"])
                )
                if dictionary_type is not None:
                    target_type = _dictionary_pg_type(dictionary_type)
                    if target_type is None:
                        raise ValueError(
                            f"Unsupported dictionary type {dictionary_type!r} "
                            f"for column {column['column_name']!r}"
                        )
                else:
                    target_type = _source_pg_type(column)
                schema_cols.append({
                    "col": column["column_name"],
                    "type": target_type,
                    "nullable": column["is_nullable"],
                })
            src_cols = [column["column_name"] for column in source_columns]

            source_table_ref = (
                f"{_quote_identifier(src_schema)}.{_quote_identifier(table)}"
            )
            row_count = 0

            bronze_name = f"{table}_bronze"   # convention: {base_name}_bronze
            stage_name = f"_{bronze_name[:38]}_{uuid4().hex[:16]}"
            col_defs = ", ".join(
                f'{_quote_identifier(column["col"])} {column["type"]}'
                for column in schema_cols
            )
            select_cols = ", ".join(
                f"{_quote_identifier(column['col'])}::{column['type']} "
                f"AS {_quote_identifier(column['col'])}"
                for column in schema_cols
            )
            select_query = f"SELECT {select_cols} FROM {source_table_ref}"
            sample_rows = []
            unlogged_setting = os.getenv("BRONZE_UNLOGGED", "true").strip().lower()
            if unlogged_setting not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
                raise ValueError("BRONZE_UNLOGGED must be a boolean value")
            stage_kind = "UNLOGGED " if unlogged_setting in {"1", "true", "yes", "on"} else ""

            async with aurum.transaction():
                await aurum.execute("CREATE SCHEMA IF NOT EXISTS bronze")
                await aurum.execute(
                    f"CREATE {stage_kind}TABLE bronze.{_quote_identifier(stage_name)} ({col_defs})"
                )
                async with src_conn.transaction():
                    cursor = await src_conn.cursor(select_query)
                    while True:
                        rows = await cursor.fetch(INGEST_BATCH_SIZE, timeout=300)
                        if not rows:
                            break
                        row_count += len(rows)
                        if len(sample_rows) < 50:
                            sample_rows.extend(
                                dict(row) for row in rows[:50 - len(sample_rows)]
                            )
                        records = (
                            tuple(row[column] for column in src_cols)
                            for row in rows
                        )
                        await aurum.copy_records_to_table(
                            stage_name, records=records, schema_name="bronze",
                            columns=src_cols,
                        )
                await aurum.execute(
                    f'DROP TABLE IF EXISTS bronze.{_quote_identifier(bronze_name)}'
                )
                await aurum.execute(
                    f"ALTER TABLE bronze.{_quote_identifier(stage_name)} "
                    f"RENAME TO {_quote_identifier(bronze_name)}"
                )
            await aurum.execute(
                f"ANALYZE bronze.{_quote_identifier(bronze_name)}"
            )
            elapsed = time.perf_counter() - table_started
            rows_per_second = row_count / elapsed if elapsed else 0.0
            log.info(
                "[bronze] engine=legacy table=bronze.%s rows=%s seconds=%.3f rows_per_second=%.0f",
                bronze_name, row_count, elapsed, rows_per_second,
            )

            if project_id:
                snapshots_exist = await aurum.fetchval(
                    "SELECT to_regclass('public.dq_schema_snapshots') IS NOT NULL"
                )
                if snapshots_exist:
                    await aurum.execute(
                        """DELETE FROM public.dq_schema_snapshots
                           WHERE project_id=$1 AND table_name=$2""",
                        project_id, bronze_name,
                    )
                    log.info(
                        "[bronze] Reset schema snapshots for typed table %s "
                        "so the next DQ run establishes a typed baseline",
                        bronze_name,
                    )

            if project_id:
                await repo.save_run(project_id, "postgres", "bronze", "PASS",
                                    row_count, row_count,
                                    {"table": bronze_name, "source": f"{src_schema}.{table}"})

            results.append({
                "source_name": table,
                "bronze_name": bronze_name,
                "base_name":   table,          # base_name == source table name for postgres
                "row_count": row_count, "col_count": len(schema_cols),
                "schema_cols": schema_cols, "sample_rows": sample_rows, "error": None,
                "seconds": elapsed, "rows_per_second": rows_per_second,
            })

        except Exception as e:
            safe_error = _redact_ingest_error(e, pg_conn)
            log.error("[bronze] Failed to ingest %s: %s", table, safe_error)
            results.append({"source_name": table, "bronze_name": f"{table}_bronze",
                             "row_count": 0, "col_count": 0,
                             "schema_cols": [], "sample_rows": [], "error": safe_error,
                             "seconds": time.perf_counter() - table_started,
                             "rows_per_second": 0.0})

    await src_conn.close()
    await aurum.close()
    return results


async def get_data_dictionary(pg_conn: dict, table: str | None = None) -> dict:
    """Read source dictionary metadata, or expose information_schema as fallback."""
    conn = await _user_conn(pg_conn)
    source_schema = pg_conn.get("schema_name") or pg_conn.get("schema") or "public"
    try:
        dictionary_rows = await _source_dictionary_rows(conn)
        if dictionary_rows is None:
            column_rows = await conn.fetch(
                """SELECT table_name, ordinal_position AS column_number,
                          column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema=$1
                     AND ($2::text IS NULL OR table_name=$2)
                   ORDER BY table_name, ordinal_position""",
                source_schema, table,
            )
            rows = [{
                "table": row["table_name"],
                "column_number": int(row["column_number"]),
                "column": row["column_name"],
                "data_type": row["data_type"],
                "expected_type": row["data_type"],
                "actual_type": row["data_type"],
                "physical_files": "",
                "matches": True,
            } for row in column_rows]
            return {
                "rows": rows,
                "row_count": len(rows),
                "fallback_used": True,
                "source": "information_schema.columns",
                "message": (
                    "metadata.data_dictionary is unavailable; showing source "
                    "information_schema.columns instead."
                ),
            }

        selected_dictionary = [
            row for row in dictionary_rows
            if table is None or str(row["logical_table"]).casefold() == table.casefold()
        ]
        view_exists = await conn.fetchval(
            "SELECT to_regclass('metadata.column_types') IS NOT NULL"
        )
        view_types = {}
        if view_exists:
            view_rows = await conn.fetch(
                """SELECT logical_table, column_name, expected_type, actual_type, matches
                   FROM metadata.column_types
                   WHERE ($1::text IS NULL OR logical_table=$1)""",
                table,
            )
            view_types = {
                (str(row["logical_table"]), str(row["column_name"])): dict(row)
                for row in view_rows
            }

        actual_rows = await conn.fetch(
            """SELECT table_name, column_name, data_type
               FROM information_schema.columns
               WHERE table_schema=$1
                 AND ($2::text IS NULL OR table_name=$2)""",
            source_schema, table,
        )
        actual_types = {
            (str(row["table_name"]), str(row["column_name"])): str(row["data_type"])
            for row in actual_rows
        }
        rows = []
        for row in selected_dictionary:
            logical_table = str(row["logical_table"])
            column_name = str(row["column_name"])
            view_row = view_types.get((logical_table, column_name), {})
            expected_type = str(view_row.get("expected_type") or row["data_type"])
            actual_type = str(
                view_row.get("actual_type")
                or actual_types.get((logical_table, column_name), "Unavailable")
            )
            matches = view_row.get("matches")
            if matches is None:
                matches = (
                    actual_type.casefold() == expected_type.casefold()
                    or (expected_type.casefold() == "text" and actual_type.casefold() == "character varying")
                )
            rows.append({
                "table": logical_table,
                "column_number": int(row["column_number"]),
                "column": column_name,
                "data_type": expected_type,
                "expected_type": expected_type,
                "actual_type": actual_type,
                "physical_files": str(row.get("physical_files") or ""),
                "matches": bool(matches),
            })
        return {
            "rows": rows,
            "row_count": len(rows),
            "fallback_used": False,
            "source": "metadata.data_dictionary",
            "message": None,
        }
    finally:
        await conn.close()


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


import json
import re
from datetime import datetime, timedelta, timezone
from app import database


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


async def check_referential_integrity(pg_conn: dict, tables: list[str]) -> list[dict]:
    """Check declared source FKs against the ingested bronze table copies."""
    source_schema = pg_conn.get("schema_name") or pg_conn.get("schema") or "public"
    selected_tables = {
        name.split(".")[-1].removesuffix("_bronze") for name in tables
    }
    source = await _user_conn(pg_conn)
    try:
        fk_rows = await source.fetch(
            """SELECT tc.table_schema, tc.table_name AS child_table,
                      kcu.column_name AS fk_column,
                      ccu.table_schema AS parent_schema,
                      ccu.table_name AS parent_table,
                      ccu.column_name AS pk_column
               FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu
                 ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
               JOIN information_schema.constraint_column_usage ccu
                 ON ccu.constraint_name = tc.constraint_name
                AND ccu.constraint_schema = tc.table_schema
               WHERE tc.constraint_type = 'FOREIGN KEY'"""
        )
        results = []
        for fk in fk_rows:
            child_table = fk["child_table"]
            if fk["table_schema"] != source_schema or child_table not in selected_tables:
                continue
            bronze_child = f"{child_table}_bronze"
            bronze_parent = f"{fk['parent_table']}_bronze"
            present = await database.fetch(
                """SELECT table_name FROM information_schema.tables
                   WHERE table_schema='bronze' AND table_name = ANY($1::text[])""",
                [bronze_child, bronze_parent],
            )
            if {row["table_name"] for row in present} != {bronze_child, bronze_parent}:
                continue

            child = f"bronze.{_quote_identifier(bronze_child)}"
            parent = f"bronze.{_quote_identifier(bronze_parent)}"
            fk_column = _quote_identifier(fk["fk_column"])
            pk_column = _quote_identifier(fk["pk_column"])
            checked_row = await database.fetch(
                f"SELECT COUNT(*) AS count FROM {child} AS c "
                f"WHERE c.{fk_column} IS NOT NULL"
            )
            failures_row = await database.fetch(
                f"SELECT COUNT(*) AS count FROM {child} AS c WHERE c.{fk_column} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM {parent} AS p "
                f"WHERE p.{pk_column} = c.{fk_column})"
            )
            rows_checked = int(checked_row[0]["count"] or 0) if checked_row else 0
            failures = int(failures_row[0]["count"] or 0) if failures_row else 0
            ri_pct = (rows_checked - failures) / rows_checked * 100.0 if rows_checked else 100.0
            results.append({
                "child_table": child_table,
                "fk_column": fk["fk_column"],
                "parent_table": fk["parent_table"],
                "pk_column": fk["pk_column"],
                "rows_checked": rows_checked,
                "fk_failures": failures,
                "ri_pct": round(ri_pct, 2),
                "status": "Pass" if failures == 0 else "Fail",
                "bronze_child_table": bronze_child,
            })
        return results
    finally:
        await source.close()


async def run_dq_check(project_id: str, tables: list[str], pg_conn: dict | None = None) -> dict:
    """Run all applicable DQ checks, score equally per check and table."""
    table_quality: list[dict] = []
    check_results: list[dict] = []
    ri_results: list[dict] = []
    rows_tested = 0

    def safe_identifier(value: str) -> str | None:
        value = value.split(".")[-1]
        return value if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) else None

    def generate_placeholder_trend(current_score: float) -> list[dict]:
        offsets = [-2.2, -1.4, -1.8, -0.7, -1.0, -0.3, 0.0]
        today = datetime.now(timezone.utc)
        return [
            {"score": round(max(0.0, min(100.0, current_score + offset)), 2),
             "timestamp": (today - timedelta(days=6 - index)).isoformat()}
            for index, offset in enumerate(offsets)
        ]

    await database.execute(
        """CREATE TABLE IF NOT EXISTS public.dq_schema_snapshots (
            snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            columns_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )

    table_checks: dict[str, list[dict]] = {}
    for requested in tables:
        requested_name = safe_identifier(requested)
        if not requested_name:
            continue
        table_name = requested_name if requested_name.endswith("_bronze") else f"{requested_name}_bronze"
        exists = await database.fetch(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='bronze' AND table_name=$1",
            table_name,
        )
        if not exists:
            continue

        columns = await database.fetch(
            """SELECT column_name AS name, data_type AS type
               FROM information_schema.columns
               WHERE table_schema='bronze' AND table_name=$1
               ORDER BY ordinal_position""",
            table_name,
        )
        column_names = [row["name"] for row in columns]
        current_schema = [{"name": row["name"], "type": row["type"]} for row in columns]
        result = await _calculate_table_quality(table_name, column_names)
        rows_tested += result["rows_tested"]
        checks = list(result["checks"])

        previous = await database.fetchrow(
            """SELECT columns_json FROM public.dq_schema_snapshots
               WHERE project_id=$1 AND table_name=$2
               ORDER BY created_at DESC LIMIT 1""",
            project_id, table_name,
        )
        previous_schema = previous["columns_json"] if previous else None
        if isinstance(previous_schema, str):
            previous_schema = json.loads(previous_schema)
        changes = []
        if previous_schema is not None:
            old_columns = {column["name"]: column["type"] for column in previous_schema}
            new_columns = {column["name"]: column["type"] for column in current_schema}
            changes.extend({"change": "added", "column": name, "type": new_columns[name]}
                           for name in new_columns.keys() - old_columns.keys())
            changes.extend({"change": "removed", "column": name, "type": old_columns[name]}
                           for name in old_columns.keys() - new_columns.keys())
            changes.extend({"change": "type_changed", "column": name,
                            "old_type": old_columns[name], "new_type": new_columns[name]}
                           for name in old_columns.keys() & new_columns.keys()
                           if old_columns[name] != new_columns[name])
        schema_passed = not changes
        schema_check = {
            "table_name": table_name,
            "column_name": "__table__",
            "inferred_type": "TABLE",
            "semantic_type": None,
            "check_name": "Schema integrity",
            "rule": "Schema integrity",
            "total_checked": 1,
            "bad_records": 0 if schema_passed else 1,
            "bad_pct": 0.0 if schema_passed else 100.0,
            "passed": schema_passed,
            "severity": check_severity(
                "Schema integrity", 0.0 if schema_passed else 100.0, schema_passed
            ),
            "count": 0 if schema_passed else 1,
            "failed_rows": [],
            "kpi_name": "Schema Changes",
            "kpi_value": changes,
        }
        checks.append(schema_check)
        await database.execute(
            """INSERT INTO public.dq_schema_snapshots (project_id, table_name, columns_json)
               VALUES ($1, $2, $3::jsonb)""",
            project_id, table_name, json.dumps(current_schema),
        )
        table_checks[table_name] = checks
        table_quality.append({
            "table_name": table_name,
            "score": 0.0,
            "passed_checks": 0,
            "total_checks": 0,
            "issue_count": 0,
            "schema_integrity": {"status": "Pass" if schema_passed else "Fail", "changes": changes},
        })

    if pg_conn:
        ri_results = await check_referential_integrity(pg_conn, tables)
        table_by_name = {table["table_name"]: table for table in table_quality}
        for relationship in ri_results:
            child_bronze = relationship.pop("bronze_child_table")
            ri_check = {
                "table_name": child_bronze,
                "column_name": relationship["fk_column"],
                "inferred_type": "REFERENTIAL",
                "semantic_type": None,
                "check_name": "Referential integrity",
                "rule": "Referential integrity",
                "total_checked": relationship["rows_checked"],
                "bad_records": relationship["fk_failures"],
                "bad_pct": round(relationship["fk_failures"] / relationship["rows_checked"] * 100, 2)
                    if relationship["rows_checked"] else 0.0,
                "passed": relationship["fk_failures"] == 0,
                "severity": check_severity(
                    "Referential integrity",
                    round(relationship["fk_failures"] / relationship["rows_checked"] * 100, 2)
                    if relationship["rows_checked"] else 0.0,
                    relationship["fk_failures"] == 0,
                ),
                "count": relationship["fk_failures"],
                "failed_rows": [],
                "kpi_name": "FK Failure Count",
                "kpi_value": relationship["fk_failures"],
            }
            if child_bronze in table_checks:
                table_checks[child_bronze].append(ri_check)
                table_by_name[child_bronze]["referential_integrity_count"] = (
                    table_by_name[child_bronze].get("referential_integrity_count", 0) + 1
                )
            else:
                check_results.append(ri_check)

    for table in table_quality:
        checks = table_checks[table["table_name"]]
        table["dimension_status"] = dimension_statuses(checks)
        table["passed_checks"] = sum(
            status == "Pass" for status in table["dimension_status"].values()
        )
        table["total_checks"] = len(QUALITY_DIMENSIONS)
        table["score"] = round(
            table["passed_checks"] / table["total_checks"] * 100, 2
        )
        table["issue_count"] = sum(
            status == "Fail" for status in table["dimension_status"].values()
        )
        check_results.extend(checks)

    total_checks = len(QUALITY_DIMENSIONS) * len(table_quality)
    passed_checks = sum(table["passed_checks"] for table in table_quality)
    dq_score = sum(table["score"] for table in table_quality) / len(table_quality) if table_quality else 0.0
    issues = [check for check in check_results if not check["passed"]]
    await database.execute(
        """CREATE TABLE IF NOT EXISTS public.dq_quality_runs (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id TEXT,
            dq_score DOUBLE PRECISION NOT NULL,
            run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    await database.execute(
        """CREATE TABLE IF NOT EXISTS public.dq_check_results (
            result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES public.dq_quality_runs(run_id) ON DELETE CASCADE,
            project_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            inferred_type TEXT NOT NULL,
            semantic_type TEXT,
            check_name TEXT NOT NULL,
            total_checked INTEGER NOT NULL,
            bad_records INTEGER NOT NULL,
            bad_pct DOUBLE PRECISION NOT NULL,
            passed BOOLEAN NOT NULL,
            severity TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    await database.execute(
        """CREATE TABLE IF NOT EXISTS public.dq_referential_integrity_results (
            result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID REFERENCES public.dq_quality_runs(run_id) ON DELETE CASCADE,
            project_id TEXT NOT NULL,
            child_table TEXT NOT NULL,
            fk_column TEXT NOT NULL,
            parent_table TEXT NOT NULL,
            pk_column TEXT NOT NULL,
            rows_checked INTEGER NOT NULL,
            fk_failures INTEGER NOT NULL,
            ri_pct DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    run_row = await database.fetchrow(
        "INSERT INTO public.dq_quality_runs (project_id, dq_score) VALUES ($1, $2) RETURNING run_id",
        project_id, round(dq_score, 2),
    )
    if run_row:
        run_id = run_row["run_id"]
        for check in check_results:
            await database.execute(
                """INSERT INTO public.dq_check_results
                   (run_id, project_id, table_name, column_name, inferred_type,
                    semantic_type, check_name, total_checked, bad_records, bad_pct,
                    passed, severity)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                run_id, project_id, check["table_name"], check["column_name"],
                check["inferred_type"], check["semantic_type"], check["check_name"],
                check["total_checked"], check["bad_records"], check["bad_pct"],
                check["passed"], check["severity"],
            )
        for relationship in ri_results:
            await database.execute(
                """INSERT INTO public.dq_referential_integrity_results
                   (run_id, project_id, child_table, fk_column, parent_table, pk_column,
                    rows_checked, fk_failures, ri_pct, status)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                run_id, project_id, relationship["child_table"], relationship["fk_column"],
                relationship["parent_table"], relationship["pk_column"],
                relationship["rows_checked"], relationship["fk_failures"],
                relationship["ri_pct"], relationship["status"],
            )

    history_rows = await database.fetch(
        """SELECT dq_score, run_timestamp FROM public.dq_quality_runs
           WHERE project_id = $1 ORDER BY run_timestamp DESC LIMIT 10""",
        project_id,
    )
    real_history = [
        {"score": float(row["dq_score"]), "timestamp": row["run_timestamp"].isoformat()}
        for row in reversed(history_rows)
    ]
    is_placeholder_data = len(real_history) < MIN_REAL_RUNS_FOR_TREND
    return {
        "dq_score": round(dq_score, 2),
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "issues_count": sum(
            check["bad_records"] for check in issues
            if check["severity"] in {"Critical", "High"}
        ),
        "warnings_count": sum(
            check["bad_records"] for check in issues
            if check["severity"] in {"Medium", "Low"}
        ),
        "rows_tested": rows_tested,
        "last_run": datetime.now(timezone.utc).isoformat(),
        "history": generate_placeholder_trend(dq_score) if is_placeholder_data else real_history,
        "is_placeholder_data": is_placeholder_data,
        "table_quality": table_quality,
        "issues": issues,
        "check_results": check_results,
        "referential_integrity": ri_results,
    }


_dq_job_registry: dict[str, dict] = {}
_dq_job_tasks: dict[str, asyncio.Task] = {}
_dq_job_lock = asyncio.Lock()


async def _ensure_dq_job_tables() -> None:
    pool = await database.get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """CREATE TABLE IF NOT EXISTS public.dq_jobs (
                job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id TEXT NOT NULL,
                status TEXT NOT NULL,
                tables JSONB NOT NULL,
                progress JSONB NOT NULL DEFAULT '{}'::jsonb,
                report JSONB,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                connection_info JSONB
            )"""
        )
        await connection.execute(
            "ALTER TABLE public.dq_jobs ADD COLUMN IF NOT EXISTS connection_info JSONB"
        )
        await connection.execute(
            """CREATE TABLE IF NOT EXISTS public.dq_schema_snapshots (
                snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                columns_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )


async def initialize_dq_jobs() -> None:
    """Create job storage and mark unfinished jobs from a prior process as failed."""
    await _ensure_dq_job_tables()
    pool = await database.get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """UPDATE public.dq_jobs
               SET status='failed', error='server restarted', finished_at=NOW()
               WHERE status='running'"""
        )


def _safe_job_connection(pg_conn: dict | None) -> dict | None:
    if not pg_conn:
        return None
    keys = ("host", "port", "database", "schema_name", "schema", "username")
    return {key: pg_conn[key] for key in keys if key in pg_conn}


async def validate_sync_dq_size(tables: list[str]) -> int:
    """Return estimated rows or reject selections that must use background jobs."""
    pool = await dq_engine_sql.get_dq_pool()
    estimates = []
    async with pool.acquire() as connection:
        for table_name in tables:
            safe_name = table_name.split(".")[-1]
            if safe_name.endswith("_bronze"):
                table = safe_name
            else:
                table = f"{safe_name}_bronze"
            metadata = await dq_engine_sql.table_metadata(connection, table)
            estimates.append(metadata["row_estimate"])
    total = sum(estimates)
    if total > MAX_SYNC_DQ_ROWS:
        raise DQReportTooLargeError(
            f"Selection is estimated at {total:,} rows; use "
            "POST /api/bronze/quality-report/jobs for large runs."
        )
    return total


async def _save_dq_job(job: dict) -> None:
    pool = await database.get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """UPDATE public.dq_jobs
               SET status=$2, progress=$3::jsonb, report=$4::jsonb, error=$5,
                   started_at=COALESCE(started_at, $6), finished_at=$7
               WHERE job_id=$1""",
            job["job_id"],
            job["status"],
            json.dumps(job["progress"]),
            json.dumps(job["report"]) if job["report"] is not None else None,
            job["error"],
            job["started_at"],
            job["finished_at"],
        )


def _json_object(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _job_response(job: dict) -> dict:
    progress = dict(job.get("progress") or {})
    partial_tables = progress.pop("partial_tables", [])
    result = {
        "job_id": str(job["job_id"]),
        "status": job["status"],
        "progress": progress,
        "partial": {"tables": partial_tables},
    }
    if job.get("status") == "completed" and job.get("report") is not None:
        result["report"] = job["report"]
    if job.get("error"):
        result["error"] = job["error"]
    return result


async def create_dq_job(
    project_id: str, tables: list[str], pg_conn: dict | None = None
) -> str:
    if not project_id:
        raise ValueError("project_id is required")
    normalized_tables = []
    for value in tables:
        name = value.split(".")[-1]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid bronze table name: {value!r}")
        normalized_tables.append(name if name.endswith("_bronze") else f"{name}_bronze")
    normalized_tables = list(dict.fromkeys(normalized_tables))
    if not normalized_tables:
        raise ValueError("At least one table is required")

    async with _dq_job_lock:
        canonical = set(normalized_tables)
        for existing in _dq_job_registry.values():
            if (
                existing["project_id"] == project_id
                and set(existing["tables"]) == canonical
                and existing["status"] in {"queued", "running"}
            ):
                return existing["job_id"]

        await _ensure_dq_job_tables()
        job_id = str(uuid4())
        now = datetime.now(timezone.utc)
        initial_progress = {
            "phase": "fast",
            "phase_label": "1/2 fast",
            "tables_total": len(normalized_tables),
            "tables_done": 0,
            "fast_tables_done": 0,
            "deep_tables_done": 0,
            "current_tables": [],
            "rows_total": 0,
            "rows_done": 0,
            "fast_rows_done": 0,
            "deep_rows_done": 0,
            "deep_rows_total": 0,
            "fast_rate_rows_s": 137000,
            "deep_rate_rows_s": 192000,
            "started_at": None,
            "elapsed_s": 0,
            "eta_s": None,
            "partial_tables": [],
        }
        safe_connection = _safe_job_connection(pg_conn)
        pool = await database.get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO public.dq_jobs
                   (job_id, project_id, status, tables, progress, connection_info)
                   VALUES ($1, $2, 'queued', $3::jsonb, $4::jsonb, $5::jsonb)""",
                job_id,
                project_id,
                json.dumps(normalized_tables),
                json.dumps(initial_progress),
                json.dumps(safe_connection) if safe_connection is not None else None,
            )
        job = {
            "job_id": job_id,
            "project_id": project_id,
            "tables": normalized_tables,
            "pg_conn": pg_conn,
            "status": "queued",
            "progress": initial_progress,
            "report": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        _dq_job_registry[job_id] = job
        _dq_job_tasks[job_id] = asyncio.create_task(_run_dq_job(job_id))
        return job_id


async def get_dq_job(job_id: str) -> dict:
    try:
        normalized_id = str(UUID(job_id))
    except ValueError as exc:
        raise ValueError("DQ job not found") from exc
    job = _dq_job_registry.get(normalized_id)
    if job is not None:
        return _job_response(job)
    pool = await database.get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT job_id, status, progress, report, error
               FROM public.dq_jobs WHERE job_id=$1""",
            UUID(normalized_id),
        )
    if row is None:
        raise ValueError("DQ job not found")
    return _job_response({
        "job_id": str(row["job_id"]),
        "status": row["status"],
        "progress": _json_object(row["progress"]) or {},
        "report": _json_object(row["report"]),
        "error": row["error"],
    })


async def cancel_dq_job(job_id: str) -> dict:
    try:
        normalized_id = str(UUID(job_id))
    except ValueError as exc:
        raise ValueError("DQ job not found") from exc
    job = _dq_job_registry.get(normalized_id)
    if job is None:
        await get_dq_job(normalized_id)
        return {"job_id": normalized_id, "status": "not_running"}
    if job["status"] in {"completed", "failed", "cancelled"}:
        return {"job_id": normalized_id, "status": job["status"]}
    task = _dq_job_tasks.get(normalized_id)
    if task is not None:
        task.cancel()
    return {"job_id": normalized_id, "status": "cancelling"}


def _table_quality_summary(table_name: str, checks: list[dict], provisional: bool) -> dict:
    statuses = dimension_statuses(checks)
    passed = sum(status == "Pass" for status in statuses.values())
    row = {
        "table_name": table_name,
        "score": round(passed / len(QUALITY_DIMENSIONS) * 100, 2),
        "passed_checks": passed,
        "total_checks": len(QUALITY_DIMENSIONS),
        "issue_count": sum(status == "Fail" for status in statuses.values()),
        "dimension_status": statuses,
        "provisional": provisional,
        "checks": _public_dq_checks(checks),
    }
    schema = next((c for c in checks if c["check_name"] == "Schema integrity"), None)
    if schema:
        row["schema_integrity"] = {
            "status": "Pass" if schema["passed"] else "Fail",
            "changes": schema["kpi_value"],
        }
    return row


def _public_dq_checks(checks: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in check.items()
         if key not in {"failed_rows", "failed_rows_truncated"}}
        for check in checks
    ]


async def _schema_integrity_check(
    connection: asyncpg.Connection, project_id: str, metadata: dict
) -> dict:
    table_name = metadata["table_name"]
    current_schema = [
        {"name": column["column_name"], "type": column["data_type"]}
        for column in metadata["columns"]
    ]
    previous = await connection.fetchrow(
        """SELECT columns_json FROM public.dq_schema_snapshots
           WHERE project_id=$1 AND table_name=$2
           ORDER BY created_at DESC LIMIT 1""",
        project_id, table_name,
    )
    previous_schema = previous["columns_json"] if previous else None
    if isinstance(previous_schema, str):
        previous_schema = json.loads(previous_schema)
    changes = []
    if previous_schema is not None:
        old = {column["name"]: column["type"] for column in previous_schema}
        new = {column["name"]: column["type"] for column in current_schema}
        changes.extend(
            {"change": "added", "column": name, "type": new[name]}
            for name in new.keys() - old.keys()
        )
        changes.extend(
            {"change": "removed", "column": name, "type": old[name]}
            for name in old.keys() - new.keys()
        )
        changes.extend(
            {"change": "type_changed", "column": name, "old_type": old[name], "new_type": new[name]}
            for name in old.keys() & new.keys() if old[name] != new[name]
        )
    passed = not changes
    return {
        "table_name": table_name,
        "column_name": "__table__",
        "inferred_type": "TABLE",
        "semantic_type": None,
        "check_name": "Schema integrity",
        "rule": "Schema integrity",
        "total_checked": 1,
        "bad_records": 0 if passed else 1,
        "bad_pct": 0.0 if passed else 100.0,
        "passed": passed,
        "severity": check_severity("Schema integrity", 0 if passed else 100, passed),
        "count": 0 if passed else 1,
        "kpi_name": "Schema Changes",
        "kpi_value": changes,
    }


async def _persist_completed_dq_job(job: dict, report: dict) -> None:
    pool = await database.get_pool()
    all_checks = report["check_results"]
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS public.dq_quality_runs (
                    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    project_id TEXT,
                    dq_score DOUBLE PRECISION NOT NULL,
                    run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
            await connection.execute(
                """CREATE TABLE IF NOT EXISTS public.dq_check_results (
                    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    run_id UUID NOT NULL REFERENCES public.dq_quality_runs(run_id) ON DELETE CASCADE,
                    project_id TEXT NOT NULL, table_name TEXT NOT NULL, column_name TEXT NOT NULL,
                    inferred_type TEXT NOT NULL, semantic_type TEXT, check_name TEXT NOT NULL,
                    total_checked INTEGER NOT NULL, bad_records INTEGER NOT NULL,
                    bad_pct DOUBLE PRECISION NOT NULL, passed BOOLEAN NOT NULL,
                    severity TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )
            run_id = await connection.fetchval(
                """INSERT INTO public.dq_quality_runs (project_id, dq_score)
                   VALUES ($1, $2) RETURNING run_id""",
                job["project_id"], report["dq_score"],
            )
            records = [
                (
                    run_id, job["project_id"], check["table_name"], check["column_name"],
                    check["inferred_type"], check.get("semantic_type"), check["check_name"],
                    check["total_checked"], check["bad_records"], check["bad_pct"],
                    check["passed"], check["severity"],
                )
                for check in all_checks
            ]
            if records:
                await connection.executemany(
                    """INSERT INTO public.dq_check_results
                       (run_id, project_id, table_name, column_name, inferred_type,
                        semantic_type, check_name, total_checked, bad_records, bad_pct,
                        passed, severity)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
                    records,
                )


async def _run_dq_job(job_id: str) -> None:
    job = _dq_job_registry[job_id]
    started = datetime.now(timezone.utc)
    job["status"] = "running"
    job["started_at"] = started
    progress = job["progress"]
    progress["started_at"] = started.isoformat()
    started_monotonic = asyncio.get_running_loop().time()
    phase_started_monotonic = started_monotonic
    current_tables: set[str] = set()
    tier1_results: dict[str, dict] = {}
    tier2_results: dict[str, dict] = {}
    metadata_by_table: dict[str, dict] = {}
    table_checks: dict[str, list[dict]] = {}
    partial_by_table: dict[str, dict] = {}
    try:
        await _save_dq_job(job)
        pool = await dq_engine_sql.get_dq_pool()
        thread_count = max(1, int(os.getenv("DQ_THREADS", str(os.cpu_count() or 1))))
        parallel_tables = max(
            1,
            int(os.getenv(
                "DQ_MAX_PARALLEL_TABLES",
                str(min(4, thread_count)),
            )),
        )
        semaphore = asyncio.Semaphore(parallel_tables)

        async def prepare(table_name: str) -> tuple[str, dict]:
            async with semaphore:
                async with pool.acquire() as connection:
                    return table_name, await dq_engine_sql.table_metadata(connection, table_name)

        prepared = await asyncio.gather(
            *(prepare(table) for table in job["tables"])
        )
        metadata_by_table.update(prepared)
        progress["rows_total"] = sum(
            metadata["row_estimate"] for metadata in metadata_by_table.values()
        )
        progress["deep_rows_total"] = progress["rows_total"]

        async def update_job_progress() -> None:
            nonlocal phase_started_monotonic
            elapsed = max(0, int(asyncio.get_running_loop().time() - started_monotonic))
            progress["elapsed_s"] = elapsed
            phase_elapsed = max(
                1.0,
                asyncio.get_running_loop().time() - phase_started_monotonic,
            )
            if progress["phase"] == "fast":
                fast_rows = progress["fast_rows_done"]
                if fast_rows:
                    progress["fast_rate_rows_s"] = max(1, int(fast_rows / phase_elapsed))
                fast_remaining = max(0, progress["rows_total"] - fast_rows)
                eta = (
                    fast_remaining / max(1, progress["fast_rate_rows_s"])
                    + progress["deep_rows_total"] / max(1, progress["deep_rate_rows_s"])
                )
            else:
                deep_rows = progress["deep_rows_done"]
                if deep_rows:
                    progress["deep_rate_rows_s"] = max(1, int(deep_rows / phase_elapsed))
                deep_remaining = max(0, progress["deep_rows_total"] - deep_rows)
                eta = deep_remaining / max(1, progress["deep_rate_rows_s"])
            progress["eta_s"] = int(eta)
            progress["current_tables"] = sorted(current_tables)
            progress["partial_tables"] = list(partial_by_table.values())
            await _save_dq_job(job)

        await update_job_progress()
        engine_name = dq_engine_sql.resolve_engine()

        async def fast(table_name: str) -> None:
            async with semaphore:
                current_tables.add(table_name)
                await update_job_progress()
                if engine_name == "sql":
                    async with pool.acquire() as connection:
                        result = await dq_engine_sql.run_tier1(
                            connection, metadata_by_table[table_name]
                        )
                else:
                    result = await _calculate_table_quality(
                        table_name,
                        [column["column_name"] for column in metadata_by_table[table_name]["columns"]],
                    )
                if engine_name == "sql":
                    schema_pool = await database.get_pool()
                    async with schema_pool.acquire() as connection:
                        schema_check = await _schema_integrity_check(
                            connection, job["project_id"], metadata_by_table[table_name]
                        )
                    result["checks"].append(schema_check)
                tier1_results[table_name] = result
                table_checks[table_name] = result["checks"]
                progress["fast_tables_done"] += 1
                progress["tables_done"] = progress["fast_tables_done"]
                progress["rows_done"] += result["rows_tested"]
                progress["fast_rows_done"] += result["rows_tested"]
                partial_by_table[table_name] = _table_quality_summary(
                    table_name, result["checks"], True
                )
                current_tables.discard(table_name)
                await update_job_progress()

        await asyncio.gather(*(fast(table) for table in job["tables"]))
        progress["phase"] = "deep"
        progress["phase_label"] = "2/2 deep"
        progress["tables_done"] = 0
        phase_started_monotonic = asyncio.get_running_loop().time()
        await update_job_progress()

        async def deep(table_name: str) -> None:
            async with semaphore:
                current_tables.add(table_name)
                await update_job_progress()
                if engine_name == "sql":
                    async with pool.acquire() as connection:
                        result = await dq_engine_sql.run_tier2(
                            connection, tier1_results[table_name]
                        )
                    tier2_results[table_name] = result
                    table_checks[table_name] = result["checks"] + [
                        check for check in tier1_results[table_name]["checks"]
                        if check["check_name"] == "Schema integrity"
                    ]
                else:
                    table_checks[table_name] = tier1_results[table_name]["checks"]
                progress["deep_tables_done"] += 1
                progress["tables_done"] = progress["deep_tables_done"]
                progress["deep_rows_done"] += metadata_by_table[table_name]["row_estimate"]
                partial_by_table[table_name] = _table_quality_summary(
                    table_name, table_checks[table_name], False
                )
                current_tables.discard(table_name)
                await update_job_progress()

        await asyncio.gather(*(deep(table) for table in job["tables"]))

        ri_results = []
        if job["pg_conn"]:
            ri_results = await check_referential_integrity(job["pg_conn"], job["tables"])
            by_name = {table: checks for table, checks in table_checks.items()}
            for relationship in ri_results:
                child = relationship["bronze_child_table"]
                ri_check = {
                    "table_name": child,
                    "column_name": relationship["fk_column"],
                    "inferred_type": "REFERENTIAL",
                    "semantic_type": None,
                    "check_name": "Referential integrity",
                    "rule": "Referential integrity",
                    "total_checked": relationship["rows_checked"],
                    "bad_records": relationship["fk_failures"],
                    "bad_pct": round(
                        relationship["fk_failures"] / relationship["rows_checked"] * 100, 2
                    ) if relationship["rows_checked"] else 0.0,
                    "passed": relationship["fk_failures"] == 0,
                    "severity": check_severity(
                        "Referential integrity",
                        round(relationship["fk_failures"] / relationship["rows_checked"] * 100, 2)
                        if relationship["rows_checked"] else 0.0,
                        relationship["fk_failures"] == 0,
                    ),
                    "count": relationship["fk_failures"],
                    "kpi_name": "FK Failure Count",
                    "kpi_value": relationship["fk_failures"],
                }
                if child in by_name:
                    by_name[child].append(ri_check)

        table_quality = [
            _table_quality_summary(table, table_checks[table], False)
            for table in job["tables"]
        ]
        checks = [check for table in job["tables"] for check in table_checks[table]]
        check_results = _public_dq_checks(checks)
        issues = [check for check in check_results if not check["passed"]]
        passed_checks = sum(table["passed_checks"] for table in table_quality)
        total_checks = len(QUALITY_DIMENSIONS) * len(table_quality)
        dq_score = (
            sum(table["score"] for table in table_quality) / len(table_quality)
            if table_quality else 0.0
        )

        schema_pool = await database.get_pool()
        async with schema_pool.acquire() as connection:
            async with connection.transaction():
                for table in job["tables"]:
                    schema = [
                        {"name": column["column_name"], "type": column["data_type"]}
                        for column in metadata_by_table[table]["columns"]
                    ]
                    await connection.execute(
                        """INSERT INTO public.dq_schema_snapshots
                           (project_id, table_name, columns_json)
                           VALUES ($1, $2, $3::jsonb)""",
                        job["project_id"], table, json.dumps(schema),
                    )

        history_rows = await database.fetch(
            """SELECT dq_score, run_timestamp FROM public.dq_quality_runs
               WHERE project_id=$1 ORDER BY run_timestamp DESC LIMIT 10""",
            job["project_id"],
        )
        history = [
            {"score": float(row["dq_score"]), "timestamp": row["run_timestamp"].isoformat()}
            for row in reversed(history_rows)
        ]
        report = {
            "dq_score": round(dq_score, 2),
            "passed_checks": passed_checks,
            "total_checks": total_checks,
            "issues_count": sum(
                check["bad_records"] for check in issues
                if check["severity"] in {"Critical", "High"}
            ),
            "warnings_count": sum(
                check["bad_records"] for check in issues
                if check["severity"] in {"Medium", "Low"}
            ),
            "rows_tested": sum(metadata["row_estimate"] for metadata in metadata_by_table.values()),
            "last_run": datetime.now(timezone.utc).isoformat(),
            "history": history,
            "is_placeholder_data": len(history) < MIN_REAL_RUNS_FOR_TREND,
            "table_quality": table_quality,
            "issues": issues,
            "check_results": check_results,
            "referential_integrity": ri_results,
        }
        if report["is_placeholder_data"]:
            offsets = [-2.2, -1.4, -1.8, -0.7, -1.0, -0.3, 0.0]
            today = datetime.now(timezone.utc)
            report["history"] = [
                {
                    "score": round(max(0.0, min(100.0, dq_score + offset)), 2),
                    "timestamp": (today - timedelta(days=6 - i)).isoformat(),
                }
                for i, offset in enumerate(offsets)
            ]
        await _persist_completed_dq_job(job, report)
        job["status"] = "completed"
        job["report"] = report
        job["progress"]["elapsed_s"] = int(
            asyncio.get_running_loop().time() - started_monotonic
        )
        job["progress"]["eta_s"] = 0
        job["progress"]["phase_label"] = "2/2 deep"
        job["progress"]["current_tables"] = []
        job["progress"]["partial_tables"] = table_quality
        job["finished_at"] = datetime.now(timezone.utc)
        await _save_dq_job(job)
    except asyncio.CancelledError:
        job["status"] = "cancelled"
        job["error"] = None
        job["finished_at"] = datetime.now(timezone.utc)
        progress["current_tables"] = []
        try:
            await _save_dq_job(job)
        finally:
            raise
    except Exception as exc:
        log.exception("DQ job %s failed", job_id)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now(timezone.utc)
        progress["current_tables"] = []
        await _save_dq_job(job)
