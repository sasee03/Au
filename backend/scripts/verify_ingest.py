"""Verify typed Bronze copies with an order-independent full-row hash."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services import bronze_service


DEFAULT_TABLES = (
    "etfs",
    "mutual_funds",
    "mutual_fund_prices_y",
    "mutual_fund_prices_f",
)


def source_connection(schema: str, database: str) -> dict:
    return {
        "host": os.getenv("SOURCE_DB_HOST", settings.AURUM_DB_HOST),
        "port": int(os.getenv("SOURCE_DB_PORT", str(settings.AURUM_DB_PORT))),
        "database": database,
        "username": os.getenv("SOURCE_DB_USER", settings.AURUM_DB_USER),
        "password": os.getenv("SOURCE_DB_PASSWORD", settings.AURUM_DB_PASSWORD),
        "schema_name": schema,
        "ssl": os.getenv("SOURCE_DB_SSL", "").lower() in {"1", "true", "yes"},
    }


async def verify_table(schema: str, database: str, table: str) -> bool:
    source = await bronze_service._user_conn(source_connection(schema, database))
    target = await bronze_service._aurum_conn()
    bronze_name = f"{table}_bronze"
    try:
        await source.execute("SET TIME ZONE 'UTC'")
        await target.execute("SET TIME ZONE 'UTC'")
        await source.execute("SET DateStyle TO 'ISO, YMD'")
        await target.execute("SET DateStyle TO 'ISO, YMD'")
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
        select_list = ", ".join(
            f"{bronze_service._quote_identifier(row['column_name'])}::{row['pg_type']} "
            f"AS {bronze_service._quote_identifier(row['column_name'])}"
            for row in columns
        )
        source_ref = (
            f"{bronze_service._quote_identifier(schema)}."
            f"{bronze_service._quote_identifier(table)}"
        )
        source_query = (
            f"SELECT COUNT(*) AS row_count, "
            f"COALESCE(SUM(hashtextextended(source_row::text, 0)::numeric), 0) AS row_hash "
            f"FROM (SELECT {select_list} FROM {source_ref}) AS source_row"
        )
        target_query = (
            f"SELECT COUNT(*) AS row_count, "
            f"COALESCE(SUM(hashtextextended(target_row::text, 0)::numeric), 0) AS row_hash "
            f'FROM bronze."{bronze_name}" AS target_row'
        )
        source_result = await source.fetchrow(source_query)
        target_result = await target.fetchrow(target_query)
        matched = (
            int(source_result["row_count"]) == int(target_result["row_count"])
            and int(source_result["row_hash"]) == int(target_result["row_hash"])
        )
        print(
            f"{table}: {'PASS' if matched else 'FAIL'} "
            f"source_rows={source_result['row_count']:,} "
            f"bronze_rows={target_result['row_count']:,} "
            f"hash_match={source_result['row_hash'] == target_result['row_hash']}"
        )
        return matched
    finally:
        await source.close()
        await target.close()


async def main(args: argparse.Namespace) -> None:
    failures = []
    for table in args.tables:
        try:
            if not await verify_table(args.schema, args.source_database, table):
                failures.append(table)
        except Exception as exc:
            failures.append(table)
            print(
                f"{table}: ERROR "
                f"{bronze_service._redact_ingest_error(exc, source_connection(args.schema, args.source_database))}"
            )
    if failures:
        raise SystemExit(f"Exactness verification failed for: {', '.join(failures)}")
    print(f"Exactness verification passed for {len(args.tables)} tables.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="usfund")
    parser.add_argument("--source-database", default="usfund")
    parser.add_argument("--tables", nargs="+", default=list(DEFAULT_TABLES))
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
