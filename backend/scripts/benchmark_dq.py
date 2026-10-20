from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pandas as pd

from app.services.bronze_service import _calculate_table_quality, database
from app.services.dq_calculation import calculate_data_quality
from app.services.dq_engine_polars import calculate_data_quality_pl


async def main() -> None:
    tables = [name for name in os.environ.get("DQ_TABLES", "").split(",") if name.strip()]
    if not tables:
        print("Set DQ_TABLES to a comma-separated list of bronze tables.")
        return
    golden_path = Path(__file__).resolve().parent / "golden_dq.json"
    if golden_path.exists():
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
    else:
        golden = []
    for table in tables:
        columns = await database.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='bronze' AND table_name=$1 ORDER BY ordinal_position",
            table,
        )
        names = [row["column_name"] for row in columns]
        records = await database.fetch(f'SELECT * FROM bronze."{table}" LIMIT 200000')
        frame = pd.DataFrame([dict(record) for record in records], columns=names)
        start = time.perf_counter()
        pandas_result = calculate_data_quality(frame, table)
        pandas_seconds = time.perf_counter() - start
        start = time.perf_counter()
        polars_result = calculate_data_quality_pl(frame, table)
        polars_seconds = time.perf_counter() - start
        print(f"{table}: pandas={pandas_seconds:.3f}s polars={polars_seconds:.3f}s speedup={pandas_seconds / max(polars_seconds, 1e-9):.2f}x")
        if golden:
            for check in pandas_result["checks"]:
                key = (table, check["column_name"], check["check_name"])
                matches = [item for item in golden if item["table"] == table and item["column"] == check["column_name"] and item["check"] == check["check_name"]]
                if matches:
                    expected = matches[0]
                    if expected["total_checked"] != check["total_checked"] or expected["bad_records"] != check["bad_records"]:
                        print(f"DIFF {key}: expected={expected}, actual={check}")


if __name__ == "__main__":
    asyncio.run(main())
