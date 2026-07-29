import logging
from fastapi import APIRouter, HTTPException, Request
from app.models.schemas import (
    SilverGenerateRequest, SilverGenerateResponse,
    SilverPreviewRequest,
    SilverExecuteRequest,  SilverExecuteResponse,
    SqlPerRule, TransformEffect,
)
from app.services import silver_service as svc

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
