"""PostgreSQL-native two-tier Bronze data-quality checks."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import asyncpg
import pandas as pd

from app.config import settings
from app.services.dq_calculation import check_severity
from app.services.dq_engine_polars import calculate_data_quality_pl

log = logging.getLogger("aurum.dq.sql")
_pool: asyncpg.Pool | None = None
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_AGGREGATES = 400

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
        parallel_tables = max(1, int(os.getenv("DQ_MAX_PARALLEL_TABLES", "4")))
        work_mem = os.getenv("DQ_PG_WORK_MEM", "256MB")
        if not re.fullmatch(r"\d+(?:kB|MB|GB)", work_mem, re.IGNORECASE):
            raise ValueError("DQ_PG_WORK_MEM must be a PostgreSQL memory value such as 256MB")
        parallel_workers = max(0, int(os.getenv("DQ_PG_PARALLEL", "4")))

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
) -> dict[str, Any]:
    pct = round(bad / total * 100, 2) if total else 0.0
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
    text_columns = []
    row_count = 0
    aggregate_columns = max(1, (_MAX_AGGREGATES - 1) // 4)

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
                text_columns.append(column)
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
        row = await connection.fetchrow(f"SELECT {', '.join(expressions)} FROM {table_ref}")
        if row is None:
            raise RuntimeError(f"Tier 1 query returned no aggregate row for {table}")
        row_count = int(row["row_count"] or 0)
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

    if text_columns and row_count:
        names = [column["column_name"] for column in text_columns]
        projection = ", ".join(quote_identifier(name) for name in names)
        pool = await get_dq_pool()
        frames: list[pd.DataFrame] = []
        async with pool.acquire() as text_connection:
            async with text_connection.transaction():
                cursor = await text_connection.cursor(
                    f"SELECT {projection} FROM {table_ref}"
                )
                while True:
                    records = await cursor.fetch(5000)
                    if not records:
                        break
                    frames.append(pd.DataFrame(
                        [dict(record) for record in records], columns=names
                    ))
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=names)
        text_result = await asyncio.to_thread(
            calculate_data_quality_pl, frame, table
        )
        checks.extend(
            check for check in text_result["checks"]
            if check["column_name"] != "__table__"
            and check["check_name"] != "Completeness"
        )
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
    for column in numeric_columns:
        name = column["column_name"]
        name_q = quote_identifier(name)
        # PostgreSQL's array percentile overload accepts double precision values.
        value_expr = f"{name_q}::double precision"
        bounds = await connection.fetchval(
            f"""SELECT percentile_cont(ARRAY[0.25, 0.75])
                        WITHIN GROUP (ORDER BY {value_expr})
                FROM {table_ref} WHERE {name_q} IS NOT NULL"""
        )
        bad = 0
        nonnull = await connection.fetchval(
            f"SELECT COUNT(*) FROM {table_ref} WHERE {name_q} IS NOT NULL"
        )
        if bounds and bounds[0] is not None and bounds[1] is not None:
            q1, q3 = float(bounds[0]), float(bounds[1])
            spread = q3 - q1
            bad = int(await connection.fetchval(
                f"""SELECT COUNT(*) FROM {table_ref}
                    WHERE {name_q} IS NOT NULL
                      AND ({value_expr} < $1 OR {value_expr} > $2)""",
                q1 - 1.5 * spread, q3 + 1.5 * spread,
            ) or 0)
        checks.append(_make_check(
            table, name, column["data_type"], "IQR outliers", int(nonnull or 0), bad,
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
