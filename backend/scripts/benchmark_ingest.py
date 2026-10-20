"""Compare Bronze PostgreSQL ingestion modes for selected tables."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services import bronze_service


async def verify_row_count(pg_conn: dict, source_schema: str, table: str, expected: int) -> None:
    source = await bronze_service._user_conn(pg_conn)
    target = await bronze_service._aurum_conn()
    try:
        source_count = await source.fetchval(
            f"SELECT COUNT(*) FROM "
            f"{bronze_service._quote_identifier(source_schema)}."
            f"{bronze_service._quote_identifier(table)}"
        )
        target_count = await target.fetchval(
            f"SELECT COUNT(*) FROM bronze."
            f"{bronze_service._quote_identifier(f'{table}_bronze')}"
        )
        if int(source_count or 0) != expected or int(target_count or 0) != expected:
            raise RuntimeError(
                f"Row-count verification failed for {table}: "
                f"source={source_count}, copied={expected}, bronze={target_count}"
            )
    finally:
        try:
            await source.close()
        finally:
            await target.close()


async def run(args: argparse.Namespace) -> None:
    pg_conn = {
        "host": os.getenv("SOURCE_DB_HOST", settings.AURUM_DB_HOST),
        "port": int(os.getenv("SOURCE_DB_PORT", str(settings.AURUM_DB_PORT))),
        "database": os.getenv("SOURCE_DB_NAME", settings.AURUM_DB_NAME),
        "username": os.getenv("SOURCE_DB_USER", settings.AURUM_DB_USER),
        "password": os.getenv("SOURCE_DB_PASSWORD", settings.AURUM_DB_PASSWORD),
        "schema_name": args.schema,
        "ssl": os.getenv("SOURCE_DB_SSL", "").lower() in {"1", "true", "yes"},
    }
    original_mode = os.environ.get("INGEST_MODE")
    timings: dict[str, dict[str, list[float]]] = {
        table: {"cursor": [], "copy": []} for table in args.tables
    }
    try:
        for table in args.tables:
            for repeat in range(args.repeat):
                modes = ("cursor", "copy") if repeat % 2 == 0 else ("copy", "cursor")
                for mode in modes:
                    os.environ["INGEST_MODE"] = mode
                    results = await bronze_service.ingest_postgres(
                        pg_conn, [table], skip_unchanged=False
                    )
                    result = results[0]
                    if result.get("error"):
                        raise RuntimeError(f"{mode} failed for {table}: {result['error']}")
                    timings[table][mode].append(result["seconds"])
                    print(
                        f"{table}: mode={mode} run={repeat + 1} "
                        f"rows={result['row_count']:,} seconds={result['seconds']:.3f} "
                        f"rows/s={result['rows_per_second']:.2f} "
                        f"MB={result['mb_loaded']:.3f}"
                    )
                    if args.verify:
                        await verify_row_count(
                            pg_conn, args.schema, table, result["row_count"]
                        )
                        print(f"{table}: {mode} row-count verification passed")
        print("\nMode comparison (mean elapsed time)")
        print(f"{'Table':35} {'Cursor (s)':>12} {'Copy (s)':>12} {'Faster':>10}")
        for table, values in timings.items():
            cursor = sum(values["cursor"]) / len(values["cursor"])
            copy = sum(values["copy"]) / len(values["copy"])
            faster = "copy" if copy < cursor else "cursor" if cursor < copy else "tie"
            print(f"{table:35} {cursor:12.3f} {copy:12.3f} {faster:>10}")
    finally:
        if original_mode is None:
            os.environ.pop("INGEST_MODE", None)
        else:
            os.environ["INGEST_MODE"] = original_mode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", nargs="+", required=True, help="Source table names to benchmark")
    parser.add_argument("--schema", default="public", help="Source schema (default: public)")
    parser.add_argument("--repeat", type=int, default=1, help="Runs per mode and table")
    parser.add_argument(
        "--verify", action="store_true",
        help="Verify source and Bronze row counts after every measured run",
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
