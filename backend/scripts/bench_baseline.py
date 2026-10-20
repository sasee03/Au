"""Measure PostgreSQL floors and Bronze ingestion/DQ baselines."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services import bronze_service, dq_engine_sql


INGEST_TABLES = (
    "etfs",
    "mutual_funds",
    "mutual_fund_prices_y",
    "etf_prices",
    "mutual_fund_prices_f",
)
DQ_TABLES = ("mutual_fund_prices_f_bronze", "mutual_funds_bronze")


def _connections(schema: str, database: str) -> dict:
    return {
        "host": os.getenv("SOURCE_DB_HOST", settings.AURUM_DB_HOST),
        "port": int(os.getenv("SOURCE_DB_PORT", str(settings.AURUM_DB_PORT))),
        "database": database,
        "username": os.getenv("SOURCE_DB_USER", settings.AURUM_DB_USER),
        "password": os.getenv("SOURCE_DB_PASSWORD", settings.AURUM_DB_PASSWORD),
        "schema_name": schema,
        "ssl": os.getenv("SOURCE_DB_SSL", "").lower() in {"1", "true", "yes"},
    }


async def measure_floors(schema: str, source_db: str) -> None:
    target = await bronze_service._aurum_conn()
    source = await bronze_service._user_conn(_connections(schema, source_db))
    table = "mutual_fund_prices_f_bronze"
    source_ref = (
        f"{bronze_service._quote_identifier(schema)}."
        f"{bronze_service._quote_identifier('mutual_fund_prices_f')}"
    )
    suffix = uuid4().hex[:12]
    logged = f"_bench_floor_logged_{suffix}"
    unlogged = f"_bench_floor_unlogged_{suffix}"
    try:
        await target.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        for name, create in (
            (logged, "CREATE TABLE"),
            (unlogged, "CREATE UNLOGGED TABLE"),
        ):
            started = time.perf_counter()
            await target.execute(
                f'{create} bronze."{name}" AS '
                f'SELECT * FROM bronze."{table}"'
            )
            print(f"floor {create.lower()}-as: {time.perf_counter() - started:.3f}s")
            await target.execute(f'DROP TABLE bronze."{name}"')

        started = time.perf_counter()
        plan = await source.fetch(
            f"EXPLAIN (ANALYZE, TIMING OFF) SELECT * FROM {source_ref}"
        )
        elapsed = time.perf_counter() - started
        print(f"floor source-read-explain: {elapsed:.3f}s")
        for row in plan:
            print(f"  {row[0]}")
    finally:
        await target.execute(f'DROP TABLE IF EXISTS bronze."{logged}"')
        await target.execute(f'DROP TABLE IF EXISTS bronze."{unlogged}"')
        await source.close()
        await target.close()


async def _peak_rss_sampler(process: psutil.Process, peak: list[int]) -> None:
    while True:
        peak[0] = max(peak[0], process.memory_info().rss)
        await asyncio.sleep(0.05)


async def measure_ingest(schema: str, source_db: str, tables: tuple[str, ...]) -> None:
    process = psutil.Process()
    pg_conn = _connections(schema, source_db)
    for table in tables:
        source = await bronze_service._user_conn(pg_conn)
        target = await bronze_service._aurum_conn()
        bronze_name = f"{table}_bronze"
        stage_name = f"_bench_ingest_{table[:35]}_{uuid4().hex[:10]}"
        source_ref = (
            f"{bronze_service._quote_identifier(schema)}."
            f"{bronze_service._quote_identifier(table)}"
        )
        start_rss = process.memory_info().rss
        peak = [start_rss]
        sampler = asyncio.create_task(_peak_rss_sampler(process, peak))
        rows_copied = 0
        started = time.perf_counter()
        try:
            columns = await target.fetch(
                """SELECT a.attname AS column_name,
                          pg_catalog.format_type(a.atttypid, a.atttypmod) AS pg_type
                   FROM pg_catalog.pg_attribute a
                   WHERE a.attrelid=$1::regclass AND a.attnum > 0
                     AND NOT a.attisdropped
                   ORDER BY a.attnum""",
                f'bronze."{bronze_name}"',
            )
            if not columns:
                raise ValueError(f"Missing Bronze table bronze.{bronze_name}")
            column_names = [row["column_name"] for row in columns]
            select_list = ", ".join(
                f"{bronze_service._quote_identifier(row['column_name'])}::"
                f"{row['pg_type']} AS "
                f"{bronze_service._quote_identifier(row['column_name'])}"
                for row in columns
            )
            await target.execute(
                f'CREATE UNLOGGED TABLE bronze."{stage_name}" '
                f'(LIKE bronze."{bronze_name}" INCLUDING DEFAULTS)'
            )
            async with source.transaction():
                cursor = await source.cursor(
                    f"SELECT {select_list} FROM {source_ref}"
                )
                while batch := await cursor.fetch(bronze_service.INGEST_BATCH_SIZE):
                    rows_copied += len(batch)
                    await target.copy_records_to_table(
                        stage_name,
                        records=(
                            tuple(row[name] for name in column_names)
                            for row in batch
                        ),
                        schema_name="bronze",
                        columns=column_names,
                    )
            elapsed = time.perf_counter() - started
            print(
                f"ingest baseline table={table} rows={rows_copied:,} "
                f"seconds={elapsed:.3f} rows_per_second={rows_copied / max(elapsed, 1e-9):.0f} "
                f"peak_rss_mb={peak[0] / 1048576:.2f} "
                f"peak_rss_delta_mb={(peak[0] - start_rss) / 1048576:.2f}"
            )
        finally:
            sampler.cancel()
            await asyncio.gather(sampler, return_exceptions=True)
            await target.execute(f'DROP TABLE IF EXISTS bronze."{stage_name}"')
            await source.close()
            await target.close()


async def measure_dq() -> None:
    statements: list[tuple[str, float]] = []
    for table in DQ_TABLES:
        connection_statements: list[tuple[str, float]] = []
        connect_started = time.perf_counter()
        connection = await bronze_service._aurum_conn()
        connect_seconds = time.perf_counter() - connect_started
        try:
            connection.add_query_logger(
                lambda record: connection_statements.append((record.query, record.elapsed))
            )
            started = time.perf_counter()
            metadata = await dq_engine_sql.table_metadata(connection, table)
            metadata_seconds = time.perf_counter() - started
            started = time.perf_counter()
            tier1 = await dq_engine_sql.run_tier1(connection, metadata)
            tier1_seconds = time.perf_counter() - started
            started = time.perf_counter()
            tier2 = await dq_engine_sql.run_tier2(connection, tier1)
            tier2_seconds = time.perf_counter() - started
        finally:
            await connection.close()
        print(
            f"dq table={table} rows={tier1['rows_tested']:,} "
            f"connect={connect_seconds:.3f}s metadata={metadata_seconds:.3f}s "
            f"tier1={tier1_seconds:.3f}s tier2={tier2_seconds:.3f}s "
            f"text-column-work=SQL aggregate; persistence=not-run"
        )
        statements.extend(connection_statements)
        print(f"  statements={len(connection_statements)} checks={len(tier2['checks'])}")

    print("DQ SQL statements, slowest first:")
    for query, elapsed in sorted(statements, key=lambda item: item[1], reverse=True)[:3]:
        print(f"  {elapsed:.3f}s {query[:220].replace(chr(10), ' ')}")


async def run(args: argparse.Namespace) -> None:
    print("AURUM benchmark baseline; credentials are not printed.")
    if not args.skip_floors:
        await measure_floors(args.schema, args.source_database)
    if not args.skip_ingest:
        await measure_ingest(args.schema, args.source_database, tuple(args.tables))
    if not args.skip_dq:
        await measure_dq()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="usfund")
    parser.add_argument("--source-database", default="usfund")
    parser.add_argument("--tables", nargs="+", default=list(INGEST_TABLES))
    parser.add_argument("--skip-floors", action="store_true")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-dq", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
