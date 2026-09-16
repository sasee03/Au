import logging
import asyncpg
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import (
    SilverGenerateRequest, SilverGenerateResponse,
    SilverPreviewRequest,
    SilverExecuteRequest,  SilverExecuteResponse,
    SqlPerRule, TransformEffect,
)
from app.services import silver_service as svc
from app.config import settings

router = APIRouter()
log    = logging.getLogger("aurum.silver_route")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


@router.post("/generate-sql", response_model=SilverGenerateResponse)
async def generate_sql(body: SilverGenerateRequest, request: Request):
    log.info(f"[silver/generate-sql] table={body.table!r} rules={len(body.rules)}")
    for i, r in enumerate(body.rules):
        log.info(f"  [{i}] {r}")
    try:
        pg = body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None
        result = await svc.generate_sql(
            table=body.table,
            rules=body.rules,
            project_id=body.project_id,
            pg_conn_cfg=pg,
        )
        items = [SqlPerRule(rule=it["rule"], sql=it["sql"]) for it in result.get("sql_per_rule", [])]
        log.info(f"[silver/generate-sql] returning {len(items)} items")
        return SilverGenerateResponse(sql_per_rule=items)
    except Exception as e:
        log.exception(f"[silver/generate-sql] ERROR: {e}")
        raise HTTPException(500, str(e))


@router.post("/preview")
async def preview_sql(body: SilverPreviewRequest):
    """Dry-run the CTE pipeline and return first 5 rows. No DB writes."""
    log.info(f"[silver/preview] table={body.table!r} sqls={len(body.sql_per_rule)}")
    try:
        pg = body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None
        result = await svc.preview_sql(
            table=body.table,
            sql_per_rule=body.sql_per_rule,
            pg_conn_cfg=pg,
        )
        if result["error"]:
            log.warning(f"[silver/preview] error: {result['error']}")
            raise HTTPException(400, result["error"])
        log.info(f"[silver/preview] row_count={result['row_count']} preview={len(result['preview_rows'])}")
        return {"preview_rows": result["preview_rows"], "row_count": result["row_count"]}
    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[silver/preview] ERROR: {e}")
        raise HTTPException(500, str(e))


@router.post("/execute", response_model=SilverExecuteResponse)
async def execute_sql(body: SilverExecuteRequest):
    log.info(f"[silver/execute] table={body.table!r} rules={len(body.rules)} sqls={len(body.sql_per_rule)}")
    try:
        pg = body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None
        result = await svc.execute_sql(
            table=body.table,
            rules=body.rules,
            sql_per_rule=body.sql_per_rule,
            project_id=body.project_id,
            pg_conn_cfg=pg,
        )
        effects = [TransformEffect(**e) for e in result["effects"]]
        log.info(f"[silver/execute] bronze={result['bronze_rows']} silver={result['silver_rows']}")
        return SilverExecuteResponse(
            bronze_rows=result["bronze_rows"],
            silver_rows=result["silver_rows"],
            affected=result["affected"],
            pct_change=result["pct_change"],
            effects=effects,
            preview_rows=result["preview_rows"],
        )
    except Exception as e:
        log.exception(f"[silver/execute] ERROR: {e}")
        raise HTTPException(500, str(e))


@router.get("/schema")
async def get_silver_schema(tables: str = ""):
    """
    Return the current silver schema as a human-readable string.
    Used by the Gold layer to get exact table and column names for AI prompting.
    Format: silver.<table_name> (col1 TYPE, col2 TYPE, ...)

    Optional query param ?tables=table1,table2 to filter to specific base names.
    This prevents stale tables from previous projects polluting the schema.
    """
    # Parse optional filter — strip schema prefix and _silver suffix to get base names
    filter_bases: set[str] = set()
    if tables.strip():
        for t in tables.split(","):
            t = t.strip().lower()
            t = t.replace("silver.", "").replace("bronze.", "")
            t = t.removesuffix("_silver").removesuffix("_bronze")
            if t:
                filter_bases.add(t)

    try:
        conn = await asyncpg.connect(
            host=settings.AURUM_DB_HOST,
            port=settings.AURUM_DB_PORT,
            database=settings.AURUM_DB_NAME,
            user=settings.AURUM_DB_USER,
            password=settings.AURUM_DB_PASSWORD,
            timeout=10,
        )
        try:
            all_tables = await conn.fetch(
                """SELECT table_name
                   FROM information_schema.tables
                   WHERE table_schema = 'silver'
                   ORDER BY table_name"""
            )
            if not all_tables:
                return {"schema_info": "", "tables": []}

            lines = []
            table_names = []
            for t in all_tables:
                tbl = t["table_name"]  # e.g. olist_orders_dataset_silver

                # Apply filter if provided: match by base name (strip _silver suffix)
                if filter_bases:
                    base = tbl.removesuffix("_silver")
                    if base not in filter_bases:
                        log.info(f"[silver/schema] skipping {tbl} (not in session selection)")
                        continue

                table_names.append(f"silver.{tbl}")
                cols = await conn.fetch(
                    """SELECT column_name, data_type
                       FROM information_schema.columns
                       WHERE table_schema = 'silver' AND table_name = $1
                       ORDER BY ordinal_position""",
                    tbl,
                )
                col_str = ", ".join(
                    f"{c['column_name']} {c['data_type'].upper()}" for c in cols
                )
                lines.append(f"silver.{tbl} ({col_str})")

            schema_info = "\n".join(lines)
            log.info(f"[silver/schema] returning {len(lines)} tables (filter={filter_bases or 'none'})")
            return {"schema_info": schema_info, "tables": table_names}
        finally:
            await conn.close()
    except Exception as e:
        log.warning(f"[silver/schema] DB error: {e}")
        raise HTTPException(500, f"Could not fetch silver schema: {e}")
