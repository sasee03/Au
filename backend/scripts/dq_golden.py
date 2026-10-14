from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from app.config import settings
from app.services.dq_calculation import calculate_data_quality
from app.services.bronze_service import database


async def main() -> None:
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='bronze' ORDER BY table_name"
        )
    rows: list[dict] = []
    for table in tables:
        table_name = table["table_name"]
        if table_name.endswith("_bronze"):
            column_rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='bronze' AND table_name=$1 ORDER BY ordinal_position",
                table_name,
            )
            columns = [row["column_name"] for row in column_rows]
            if not columns:
                continue
            data = await conn.fetch(f'SELECT * FROM bronze."{table_name}" LIMIT 200000')
            if len(data) > 2_000_000:
                print(f"Skipping {table_name}: >2,000,000 rows")
                continue
            frame = pd.DataFrame([dict(record) for record in data], columns=columns)
            result = calculate_data_quality(frame, table_name)
            for check in result["checks"]:
                rows.append({
                    "table": table_name,
                    "column": check["column_name"],
                    "check": check["check_name"],
                    "total_checked": check["total_checked"],
                    "bad_records": check["bad_records"],
                    "passed": check["passed"],
                })
    out = Path(__file__).resolve().parent / "golden_dq.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
