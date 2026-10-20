from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.services import bronze_service, dq_engine_sql

PARITY_TABLES = (
    "etfs_bronze",
    "mutual_funds_bronze",
    "mutual_fund_prices_y_bronze",
    "mutual_fund_prices_z_bronze",
    "mutual_fund_prices_f_bronze",
)


def keyed(checks: list[dict]) -> dict[tuple, dict]:
    return {
        (check["table_name"], check["column_name"], check["check_name"]): check
        for check in checks
    }


async def main() -> None:
    await database.init_db()
    differences = []
    try:
        pool = await dq_engine_sql.get_dq_pool()
        for table in PARITY_TABLES:
            async with pool.acquire() as connection:
                metadata = await dq_engine_sql.table_metadata(connection, table)
                fast = await dq_engine_sql.run_tier1(connection, metadata)
                sql_result = await dq_engine_sql.run_tier2(connection, fast)

            os.environ["DQ_ENGINE"] = "polars"
            polars_result = await bronze_service._calculate_table_quality(
                table,
                [column["column_name"] for column in metadata["columns"]],
            )
            sql_checks = keyed(sql_result["checks"])
            polars_checks = keyed(polars_result["checks"])
            for key in sorted(sql_checks.keys() | polars_checks.keys()):
                sql_check = sql_checks.get(key)
                polars_check = polars_checks.get(key)
                if sql_check is None or polars_check is None:
                    differences.append((key, "missing check", sql_check, polars_check))
                    continue
                fields = ("total_checked", "bad_records", "passed")
                if any(sql_check[field] != polars_check[field] for field in fields):
                    differences.append((key, "value mismatch", sql_check, polars_check))
        if differences:
            print(f"PARITY FAILED: {len(differences)} differences")
            for key, reason, sql_check, polars_check in differences:
                print(
                    f"{reason}: {key}; SQL={sql_check}; "
                    f"Polars={polars_check}"
                )
        else:
            print(f"PARITY PASSED: zero diffs across {len(PARITY_TABLES)} tables")
    finally:
        await dq_engine_sql.close_dq_pool()
        await database.close_db()
    if differences:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
