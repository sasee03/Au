"""PostgreSQL-native two-tier Bronze data-quality checks."""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import asyncpg

from app.config import settings
from app.services.dq_calculation import check_severity

log = logging.getLogger("aurum.dq.sql")
_pool: asyncpg.Pool | None = None
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_AGGREGATES = 1600
_DATE_SHAPE = (
    r"([0-9]{1,4}[-/][0-9]{1,2}([- /][0-9]{1,4})?|"
    r"[0-9]{1,4}\.[0-9]{1,2}\.[0-9]{1,4}|"
    r"[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?|"
    r"^[0-9]{8}$|^[0-9]{4}$|"
    r"[0-9]{1,2}[[:space:]]+[A-Za-z]{3,}|"
    r"[0-9]{4}[[:space:]]+[A-Za-z]{3,}|"
    r"[A-Za-z]{3,}[[:space:]]+[0-9]{1,2})"
)
_WARNED_ENGINE_FALLBACKS: set[str] = set()

def resolve_engine() -> str:
    requested = os.getenv("DQ_ENGINE", "auto").strip().lower()
    if requested in {"auto", "sql"}:
        return "sql"
    if requested in {"polars", "pandas"}:
        return requested
    if requested == "duckdb":
        message = f"DQ engine {requested!r} is unavailable; falling back to sql"
    else:
        message = f"Unknown DQ engine {requested!r}; falling back to sql"
    if requested not in _WARNED_ENGINE_FALLBACKS:
        log.warning(message)
        _WARNED_ENGINE_FALLBACKS.add(requested)
    return "sql"

NUMERIC_TYPES = {
    "smallint", "integer", "bigint", "decimal", "numeric",
    "real", "double precision", "smallserial", "serial", "bigserial",
}
DATE_TYPES = {"date", "timestamp without time zone", "timestamp with time zone"}
TEXT_TYPES = {"text", "character varying", "character", "name"}


def quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe PostgreSQL identifier: {value!r}")
    return f'"{value}"'


async def get_dq_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        thread_count = max(1, int(os.getenv("DQ_THREADS", str(os.cpu_count() or 1))))
        parallel_tables = max(
            1,
            int(os.getenv(
                "DQ_MAX_PARALLEL_TABLES",
                str(min(4, thread_count)),
            )),
        )
        work_mem = os.getenv("DQ_PG_WORK_MEM", "256MB")
        if not re.fullmatch(r"\d+(?:kB|MB|GB)", work_mem, re.IGNORECASE):
            raise ValueError("DQ_PG_WORK_MEM must be a PostgreSQL memory value such as 256MB")
        default_workers = max(0, thread_count // parallel_tables - 1)
        parallel_workers = max(
            0,
            int(os.getenv("DQ_PG_PARALLEL", str(default_workers))),
        )
        if parallel_tables * (parallel_workers + 1) > thread_count:
            raise ValueError(
                "DQ_MAX_PARALLEL_TABLES multiplied by DQ_PG_PARALLEL + 1 "
                "must not exceed DQ_THREADS"
            )

        async def initialize(connection: asyncpg.Connection) -> None:
            await connection.execute(f"SET work_mem = '{work_mem}'")
            await connection.execute(
                f"SET max_parallel_workers_per_gather = {parallel_workers}"
            )

        _pool = await asyncpg.create_pool(
            host=settings.AURUM_DB_HOST,
            port=settings.AURUM_DB_PORT,
            database=settings.AURUM_DB_NAME,
            user=settings.AURUM_DB_USER,
            password=settings.AURUM_DB_PASSWORD,
            min_size=1,
            max_size=parallel_tables + 1,
            command_timeout=None,
            init=initialize,
        )
    return _pool


async def close_dq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _make_check(
    table: str,
    column: str,
    inferred_type: str,
    name: str,
    total: int,
    bad: int,
    *,
    kpi_name: str | None = None,
    kpi_value: Any = None,
    bad_pct: float | None = None,
) -> dict[str, Any]:
    pct = (
        round(bad / total * 100, 2) if total else 0.0
    ) if bad_pct is None else bad_pct
    passed = bad == 0
    return {
        "table_name": table,
        "column_name": column,
        "inferred_type": inferred_type,
        "semantic_type": None,
        "check_name": name,
        "rule": name,
        "total_checked": int(total),
        "bad_records": int(bad),
        "bad_pct": pct,
        "passed": passed,
        "severity": check_severity(name, pct, passed),
        "count": int(bad),
        "kpi_name": kpi_name,
        "kpi_value": kpi_value,
    }


async def table_metadata(connection: asyncpg.Connection, table: str) -> dict[str, Any]:
    table_q = quote_identifier(table)
    columns = await connection.fetch(
        """SELECT column_name, data_type, udt_name
           FROM information_schema.columns
           WHERE table_schema='bronze' AND table_name=$1
           ORDER BY ordinal_position""",
        table,
    )
    if not columns:
        raise ValueError(f"Bronze table {table!r} does not exist or has no columns")
    estimate = await connection.fetchval(
        """SELECT c.reltuples
           FROM pg_class c
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='bronze' AND c.relname=$1""",
        table,
    )
    if estimate is None or estimate < 0:
        await connection.execute(f"ANALYZE bronze.{table_q}")
        estimate = await connection.fetchval(
            """SELECT c.reltuples FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='bronze' AND c.relname=$1""",
            table,
        )
    return {
        "table_name": table,
        "columns": [dict(row) for row in columns],
        "row_estimate": max(0, int(estimate or 0)),
    }


def _kind(column: dict[str, Any]) -> str:
    data_type = column["data_type"].lower()
    if data_type in NUMERIC_TYPES:
        return "numeric"
    if data_type in DATE_TYPES:
        return "date"
    if data_type == "boolean":
        return "boolean"
    if data_type in TEXT_TYPES or column["udt_name"] in {"varchar", "bpchar", "text", "name"}:
        return "text"
    return "other"


async def run_tier1(
    connection: asyncpg.Connection, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Compute quick column checks with bounded aggregate target lists."""
    table = metadata["table_name"]
    table_ref = f'bronze.{quote_identifier(table)}'
    columns = metadata["columns"]
    checks: list[dict[str, Any]] = []
    row_count = 0
    aggregate_columns = max(1, (_MAX_AGGREGATES - 1) // 9)

    for start in range(0, len(columns), aggregate_columns):
        subset = columns[start:start + aggregate_columns]
        expressions = ["COUNT(*) AS row_count"]
        for index, column in enumerate(subset):
            name = column["column_name"]
            name_q = quote_identifier(name)
            kind = _kind(column)
            expressions.append(
                f"COUNT(*) FILTER (WHERE {name_q} IS NULL) AS c{index}_null"
            )
            if kind == "text":
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL "
                    f"AND BTRIM({name_q}::text) = '') AS c{index}_blank"
                )
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL "
                    f"AND BTRIM({name_q}::text) <> '') AS c{index}_nonblank"
                )
                expressions.append(f"MIN({name_q}::text) AS c{index}_min")
                expressions.append(f"MAX({name_q}::text) AS c{index}_max")
            elif kind == "numeric":
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL) AS c{index}_nonnull"
                )
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL AND {name_q} >= 0) "
                    f"AS c{index}_nonnegative"
                )
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} < 0) AS c{index}_negative"
                )
            elif kind == "date":
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL) AS c{index}_nonnull"
                )
                expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} < TIMESTAMP '1900-01-01' "
                    f"OR {name_q} > NOW() + INTERVAL '1 year') AS c{index}_range_bad"
                )
        statement = f"SELECT {', '.join(expressions)} FROM {table_ref}"
        started = time.perf_counter()
        row = await connection.fetchrow(statement)
        duration = time.perf_counter() - started
        log.info(
            "[dq] table=%s phase=tier1 sql_seconds=%.3f columns=%d",
            table, duration, len(subset),
        )
        if row is None:
            raise RuntimeError(f"Tier 1 query returned no aggregate row for {table}")
        row_count = int(row["row_count"] or 0)
        variable_text_columns = [
            (index, column)
            for index, column in enumerate(subset)
            if _kind(column) == "text"
            and row_count
            and row_count - int(row[f"c{index}_null"] or 0) > 0
            and row[f"c{index}_min"] != row[f"c{index}_max"]
        ]
        text_shapes: dict[int, dict[str, int]] = {}
        if variable_text_columns:
            shape_expressions = []
            for index, column in variable_text_columns:
                name_q = quote_identifier(column["column_name"])
                text_value = f"BTRIM({name_q}::text)"
                shape_expressions.extend((
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL "
                    f"AND {text_value} ~ "
                    r"'^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$') "
                    f"AS n{index}",
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL "
                    f"AND {text_value} ~ '{_DATE_SHAPE}') AS d{index}",
                ))
            shape_statement = (
                f"SELECT {', '.join(shape_expressions)} FROM {table_ref}"
            )
            started = time.perf_counter()
            shape_row = await connection.fetchrow(shape_statement)
            log.info(
                "[dq] table=%s phase=tier1_text_shape sql_seconds=%.3f columns=%d",
                table, time.perf_counter() - started, len(variable_text_columns),
            )
            text_shapes = {
                index: {
                    "numeric": int(shape_row[f"n{index}"] or 0),
                    "date": int(shape_row[f"d{index}"] or 0),
                }
                for index, _ in variable_text_columns
            }
        date_candidates = [
            (index, column)
            for index, column in variable_text_columns
            if text_shapes[index]["date"] / row_count > 0.5
        ]
        date_valid_counts: dict[int, int] = {}
        if date_candidates:
            date_expressions = []
            for index, column in date_candidates:
                name_q = quote_identifier(column["column_name"])
                text_value = f"BTRIM({name_q}::text)"
                date_expressions.append(
                    f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL "
                    f"AND {text_value} <> '' "
                    f"AND CASE WHEN {text_value} ~ '{_DATE_SHAPE}' "
                    f"THEN pg_input_is_valid({text_value}, 'timestamptz') "
                    f"ELSE FALSE END) AS d{index}"
                )
            date_statement = (
                f"SELECT {', '.join(date_expressions)} FROM {table_ref}"
            )
            started = time.perf_counter()
            date_row = await connection.fetchrow(date_statement)
            log.info(
                "[dq] table=%s phase=tier1_text_date sql_seconds=%.3f columns=%d",
                table, time.perf_counter() - started, len(date_candidates),
            )
            date_valid_counts = {
                index: int(date_row[f"d{index}"] or 0)
                for index, _ in date_candidates
            }
        for index, column in enumerate(subset):
            name = column["column_name"]
            kind = _kind(column)
            null_count = int(row[f"c{index}_null"] or 0)
            blank_count = int(row.get(f"c{index}_blank", 0) or 0)
            checks.append(_make_check(
                table, name, column["data_type"], "Completeness", row_count,
                null_count + blank_count,
            ))
            if kind == "numeric":
                nonnull = int(row[f"c{index}_nonnull"] or 0)
                nonnegative = int(row[f"c{index}_nonnegative"] or 0)
                if nonnull and nonnegative / nonnull > 0.95:
                    checks.append(_make_check(
                        table, name, column["data_type"], "Negative values", nonnull,
                        int(row[f"c{index}_negative"] or 0),
                    ))
            elif kind == "date":
                nonnull = int(row[f"c{index}_nonnull"] or 0)
                checks.append(_make_check(
                    table, name, column["data_type"], "Logical date range", nonnull,
                    int(row[f"c{index}_range_bad"] or 0),
                ))
                checks.append(_make_check(
                    table, name, column["data_type"], "Date parse validity", nonnull, 0,
                ))
            elif kind == "text":
                nonblank = int(row[f"c{index}_nonblank"] or 0)
                numeric_shape = text_shapes.get(index, {}).get("numeric", 0)
                date_valid = date_valid_counts.get(index, 0)
                numeric_rate = numeric_shape / nonblank if nonblank else 0
                date_rate = date_valid / (row_count - null_count) if row_count > null_count else 0
                if numeric_rate > 0.5 and date_rate <= 0.5:
                    checks.append(_make_check(
                        table, name, "TEXT", "Numeric type consistency", nonblank,
                        nonblank - numeric_shape,
                    ))
                elif date_rate > 0.5:
                    checks.append(_make_check(
                        table, name, "DATE", "Date format validity", nonblank,
                        nonblank - date_valid,
                    ))
                elif (
                    row_count - null_count > 0
                    and row[f"c{index}_min"] == row[f"c{index}_max"]
                ):
                    constant = _make_check(
                        table, name, "TEXT", "Constant column warning", 1, 1,
                        bad_pct=0.0,
                    )
                    checks.append(constant)
    return {
        "table_name": table,
        "rows_tested": row_count,
        "checks": checks,
        "metadata": metadata,
    }


async def run_tier2(
    connection: asyncpg.Connection, tier1: dict[str, Any]
) -> dict[str, Any]:
    """Compute statistics-heavy checks after all tables finish Tier 1."""
    table = tier1["table_name"]
    table_ref = f'bronze.{quote_identifier(table)}'
    metadata = tier1["metadata"]
    row_count = tier1["rows_tested"]
    checks = list(tier1["checks"])
    columns = metadata["columns"]
    numeric_columns = [column for column in columns if _kind(column) == "numeric"]
    if numeric_columns:
        bounds = []
        for index, column in enumerate(numeric_columns):
            name_q = quote_identifier(column["column_name"])
            bounds.append(
                f"percentile_cont(ARRAY[0.25, 0.75]) "
                f"WITHIN GROUP (ORDER BY {name_q}::double precision) AS q{index}"
            )
        stats = []
        for index, column in enumerate(numeric_columns):
            name_q = quote_identifier(column["column_name"])
            stats.extend((
                f"COUNT(*) FILTER (WHERE {name_q} IS NOT NULL) AS c{index}_nonnull",
                f"""COUNT(*) FILTER (
                    WHERE {name_q} IS NOT NULL
                      AND (b.q{index} IS NOT NULL)
                      AND ({name_q}::double precision
                           < b.q{index}[1] - 1.5 * (b.q{index}[2] - b.q{index}[1])
                        OR {name_q}::double precision
                           > b.q{index}[2] + 1.5 * (b.q{index}[2] - b.q{index}[1]))
                ) AS c{index}_outliers""",
            ))
        statement = (
            f"WITH bounds AS (SELECT {', '.join(bounds)} FROM {table_ref}), "
            f"stats AS (SELECT {', '.join(stats)} FROM {table_ref} CROSS JOIN bounds b "
            f"GROUP BY {', '.join(f'b.q{i}' for i in range(len(numeric_columns)))}) "
            "SELECT * FROM stats"
        )
        started = time.perf_counter()
        numeric_stats = await connection.fetchrow(statement)
        log.info(
            "[dq] table=%s phase=tier2_iqr sql_seconds=%.3f numeric_columns=%d",
            table, time.perf_counter() - started, len(numeric_columns),
        )
        for index, column in enumerate(numeric_columns):
            name = column["column_name"]
            nonnull = int(numeric_stats[f"c{index}_nonnull"] or 0)
            bad = int(numeric_stats[f"c{index}_outliers"] or 0)
            checks.append(_make_check(
                table, name, column["data_type"], "IQR outliers", nonnull, bad,
            ))

    if row_count:
        column_names = [column["column_name"] for column in columns]
        grouping = ", ".join(quote_identifier(name) for name in column_names)
        duplicate_query = (
            f"SELECT $1::bigint - COUNT(*) FROM "
            f"(SELECT 1 FROM {table_ref} GROUP BY {grouping}) AS groups"
        )
        if os.getenv("DQ_EXPLAIN") == "1":
            plan = await connection.fetch(
                f"EXPLAIN (ANALYZE, BUFFERS) {duplicate_query}", row_count
            )
            log.info("Duplicate check plan for bronze.%s: %s", table, "\n".join(r[0] for r in plan))
        duplicate_count = int(await connection.fetchval(duplicate_query, row_count) or 0)
        checks.append(_make_check(
            table, "__table__", "TABLE", "Full-row duplicates", row_count, duplicate_count,
            kpi_name="% Unique",
            kpi_value=round((row_count - duplicate_count) / row_count * 100, 2),
        ))
    return {
        "table_name": table,
        "rows_tested": row_count,
        "checks": checks,
    }
