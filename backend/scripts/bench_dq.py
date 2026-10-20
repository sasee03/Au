"""Benchmark available SQL Bronze DQ phases."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import bronze_service, dq_engine_sql


DEFAULT_TABLES = (
    "etfs_bronze",
    "mutual_funds_bronze",
    "mutual_fund_prices_y_bronze",
    "mutual_fund_prices_z_bronze",
    "mutual_fund_prices_f_bronze",
)


async def run(tables: list[str]) -> None:
    print(f"Available benchmark engine: {dq_engine_sql.resolve_engine()}")
    for table in tables:
        statements: list[tuple[str, float]] = []
        connection = await bronze_service._aurum_conn()
        try:
            connection.add_query_logger(
                lambda record: statements.append((record.query, record.elapsed))
            )
            started = time.perf_counter()
            metadata = await dq_engine_sql.table_metadata(connection, table)
            metadata_seconds = time.perf_counter() - started
            started = time.perf_counter()
            tier1 = await dq_engine_sql.run_tier1(connection, metadata)
            tier1_seconds = time.perf_counter() - started
            started = time.perf_counter()
            result = await dq_engine_sql.run_tier2(connection, tier1)
            tier2_seconds = time.perf_counter() - started
        finally:
            await connection.close()

        rows = tier1["rows_tested"]
        print(
            f"{table}: rows={rows:,} columns={len(metadata['columns'])} "
            f"metadata={metadata_seconds:.3f}s tier1={tier1_seconds:.3f}s "
            f"tier1_rows_per_second={rows / max(tier1_seconds, 1e-9):.0f} "
            f"tier2={tier2_seconds:.3f}s statements={len(statements)} "
            f"checks={len(result['checks'])}"
        )
        for query, elapsed in sorted(statements, key=lambda item: item[1], reverse=True)[:3]:
            print(f"  sql_seconds={elapsed:.3f} sql={query[:180].replace(chr(10), ' ')}")


async def main(args: argparse.Namespace) -> None:
    if args.full:
        connection = await bronze_service._aurum_conn()
        try:
            rows = await connection.fetch(
                """SELECT table_name FROM information_schema.tables
                   WHERE table_schema='bronze' AND table_type='BASE TABLE'
                     AND LEFT(table_name, 7) <> '_bench_'
                   ORDER BY table_name"""
            )
        finally:
            await connection.close()
        tables = [row["table_name"] for row in rows]
    else:
        tables = args.tables or list(DEFAULT_TABLES)
    await run(tables)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", nargs="+", help="Bronze table names")
    parser.add_argument(
        "--full", action="store_true",
        help="Benchmark every non-benchmark Bronze table",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
