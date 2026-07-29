import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    GoldGenerateRequest, GoldGenerateResponse,
    GoldExecuteRequest,  GoldExecuteResponse,
    KpiItem,
)
from app.services import gold_service as svc

router = APIRouter()
log    = logging.getLogger("aurum.gold_route")


@router.get("/preview")
async def preview_gold_table(table: str):
    """Return first 5 rows of a gold table by bare name (without schema prefix)."""
    log.info(f"[gold/preview] table={table!r}")
    try:
        import asyncpg
        from app.config import settings
        conn = await asyncpg.connect(
            host=settings.AURUM_DB_HOST, port=settings.AURUM_DB_PORT,
            database=settings.AURUM_DB_NAME, user=settings.AURUM_DB_USER,
            password=settings.AURUM_DB_PASSWORD, timeout=10,
        )
        # strip schema prefix if passed as gold.xxx
        bare = table.replace("gold.", "")
        try:
            rows = await conn.fetch(f'SELECT * FROM gold."{bare}" LIMIT 5')
            result = [dict(r) for r in rows]
        finally:
            await conn.close()
        return {"rows": result, "table": bare}
    except Exception as e:
        log.warning(f"[gold/preview] failed: {e}")
        raise HTTPException(400, str(e))


@router.post("/generate-kpi", response_model=GoldGenerateResponse)
async def generate_kpi(body: GoldGenerateRequest):
    log.info(f"[gold/generate-kpi] requirement={body.requirement!r:.80}")
    try:
        pg = body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None
        result = await svc.generate_kpi_plan(
            requirement=body.requirement,
            project_id=body.project_id,
            schema_info=body.schema_info or "",
            pg_conn_cfg=pg,
        )
        kpis = [KpiItem(**k) for k in result.get("kpis", [])]
        log.info(f"[gold/generate-kpi] returning {len(kpis)} KPIs")
        return GoldGenerateResponse(kpis=kpis)
    except Exception as e:
        log.exception(f"[gold/generate-kpi] ERROR: {e}")
        raise HTTPException(500, str(e))


@router.post("/execute", response_model=GoldExecuteResponse)
async def execute_gold(body: GoldExecuteRequest):
    log.info(f"[gold/execute] kpis={len(body.kpis)}")
    try:
        pg        = body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None
        kpis_list = [k.model_dump() for k in body.kpis]
        result    = await svc.execute_gold(
            project_id=body.project_id,
            requirement=body.requirement,
            kpis=kpis_list,
            pg_conn_cfg=pg,
            base_name=body.base_name,
        )
        log.info(f"[gold/execute] tables_created={result['tables_created']}")
        return GoldExecuteResponse(**result)
    except Exception as e:
        log.exception(f"[gold/execute] ERROR: {e}")
        raise HTTPException(500, str(e))
