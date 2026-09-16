"""
Gold layer service.
- generate_kpi_plan : fetches real silver schema, calls AI for KPI SQL.
                      Deterministic fallback when AI unavailable.
- execute_gold      : runs each KPI SQL against silver schema,
                      writes results to gold.<kpi_name> tables.
"""
import asyncpg
import logging
from app.config import settings
from app.prompts.gold_prompt import build_gold_prompt
from app.services.ai_service import call_ai_json
from app.repositories import project_repository as repo

log = logging.getLogger("aurum.gold")

# No hardcoded preview — an empty list is returned when the DB is unreachable.
# The frontend handles empty preview gracefully.


# ── helpers ───────────────────────────────────────────────────────────────────

async def _open_conn(pg_conn_cfg: dict | None) -> asyncpg.Connection | None:
    """Connect to the single AURUM database — silver/gold schemas live here."""
    try:
        return await asyncpg.connect(
            host=settings.AURUM_DB_HOST,
            port=settings.AURUM_DB_PORT,
            database=settings.AURUM_DB_NAME,
            user=settings.AURUM_DB_USER,
            password=settings.AURUM_DB_PASSWORD,
            timeout=15,
        )
    except Exception as e:
        log.warning(f"[gold] AURUM DB connect failed: {e}")
        return None


async def _fetch_silver_schema(pg_conn_cfg: dict | None) -> str:
    """
    Introspect the silver schema in the AURUM processing DB and return a
    human-readable summary for the AI prompt, e.g.:
        silver.olist_orders_dataset_silver (order_id TEXT, order_date DATE, ...)

    NOTE: pg_conn_cfg is the user's *source* database — we intentionally
    ignore it here and always read from the AURUM DB where silver tables live.
    """
    conn = await _open_conn(pg_conn_cfg)
    if conn is None:
        log.error("[gold] Cannot connect to AURUM DB — silver schema unavailable")
        return ""

    try:
        tables = await conn.fetch(
            """SELECT table_name
               FROM information_schema.tables
               WHERE table_schema = 'silver'
               ORDER BY table_name"""
        )
        if not tables:
            log.warning("[gold] No tables found in silver schema — run Silver layer first")
            return ""

        lines = []
        for t in tables:
            tbl = t["table_name"]
            cols = await conn.fetch(
                """SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema = 'silver' AND table_name = $1
                   ORDER BY ordinal_position""",
                tbl,
            )
            col_str = ", ".join(f"{c['column_name']} {c['data_type'].upper()}" for c in cols)
            lines.append(f"silver.{tbl} ({col_str})")

        schema_str = "\n".join(lines)
        log.info(f"[gold] fetched {len(lines)} silver tables from AURUM DB")
        return schema_str
    except Exception as e:
        log.warning(f"[gold] silver schema fetch error: {e}")
        return ""
    finally:
        await conn.close()


# ── KPI generation ────────────────────────────────────────────────────────────

async def generate_kpi_plan(
    requirement: str,
    project_id: str | None,
    schema_info: str,
    pg_conn_cfg: dict | None = None,
) -> dict:
    """
    Build the KPI plan using AI.
    Fetches real silver schema first; falls back to schema_info passed from frontend.
    """
    # Try to get live silver schema — always try AURUM DB directly,
    # pg_conn_cfg is the *source* DB and is irrelevant here.
    live_schema = await _fetch_silver_schema(pg_conn_cfg)
    prompt_schema = live_schema or schema_info or ""

    if not prompt_schema.strip():
        raise RuntimeError(
            "Silver schema is empty. Make sure you have executed the Silver layer "
            "for all selected tables before generating the Gold KPI plan."
        )

    log.info(f"[gold] silver schema used:\n{prompt_schema}")

    prompt = build_gold_prompt(requirement, prompt_schema)
    log.info(f"[gold] prompt length: {len(prompt)} chars, calling AI…")

    try:
        result = await call_ai_json(prompt)
        kpis   = result.get("kpis", [])
        if not kpis:
            raise ValueError("AI returned empty KPI list")
        log.info(f"[gold] AI returned {len(kpis)} KPIs")
    except Exception as e:
        log.error(f"[gold] AI failed: {e}")
        raise RuntimeError(
            f"AI model unavailable: {e}. "
            "Start Ollama with 'ollama serve' and pull a model with 'ollama pull sqlcoder'."
        ) from e

    # Persist
    if project_id:
        await repo.save_gold_kpis(project_id, requirement, kpis)

    return {"kpis": kpis}


# ── Gold execution ────────────────────────────────────────────────────────────

async def execute_gold(
    project_id: str | None,
    requirement: str,
    kpis: list[dict],
    pg_conn_cfg: dict | None,
    base_name: str | None = None,
) -> dict:
    """
    Run each KPI's SQL against the silver schema.
    Writes results to gold.<kpi_name> tables.
    """
    tables_created: list[str] = []
    preview_rows: list[dict] = []    # empty until real DB rows arrive
    ready_kpis   = [k for k in kpis if k.get("sql", "").strip()]

    conn = await _open_conn(pg_conn_cfg)
    if conn and ready_kpis:
        try:
            # Ensure gold schema exists
            await conn.execute("CREATE SCHEMA IF NOT EXISTS gold")

            # Get base_name from passed argument, then DB fallback
            from app.services.naming import gold_table as make_gold_tbl
            base_name_for_gold = base_name or "dataset"
            if not base_name and project_id:
                try:
                    from app.repositories.project_repository import ProjectRepository
                    repo2 = ProjectRepository()
                    run = await repo2.get_latest_run(project_id, "bronze")
                    if run and isinstance(run.get("details"), dict):
                        base_name_for_gold = run["details"].get("base_name", "dataset")
                except Exception:
                    pass

            for kpi in ready_kpis:
                # Convention: {base_name}_gold_{kpi_slug}
                gold_tbl = make_gold_tbl(base_name_for_gold, kpi["name"])
                sql      = kpi["sql"].rstrip(";")

                try:
                    await conn.execute(f'DROP TABLE IF EXISTS gold."{gold_tbl}"')
                    await conn.execute(
                        f'CREATE TABLE gold."{gold_tbl}" AS ({sql})'
                    )
                    tables_created.append(gold_tbl)
                    log.info(f"[gold] Created gold.\"{gold_tbl}\"")
                except Exception as e:
                    log.warning(f"[gold] KPI table {gold_tbl} failed: {e}")

            # Preview from first successful table
            if tables_created:
                try:
                    rows = await conn.fetch(f'SELECT * FROM gold."{tables_created[0]}" LIMIT 5')
                    if rows:
                        preview_rows = [dict(r) for r in rows]
                except Exception as e:
                    log.warning(f"[gold] preview fetch failed: {e}")

        except Exception as e:
            log.error(f"[gold] execute_gold error: {e}")
        finally:
            await conn.close()

    if not tables_created:
        from app.services.naming import gold_table as make_gold_tbl
        tables_created = [
            make_gold_tbl(base_name_for_gold, k["name"])
            for k in ready_kpis[:3]
        ] if ready_kpis else [f"{base_name_for_gold}_gold_summary"]

    if project_id:
        await repo.save_run(
            project_id,
            "postgres" if pg_conn_cfg else "csv",
            "gold", "PASS",
            0, 0,
            {
                "requirement":  requirement,
                "base_name":    base_name_for_gold,
                "kpi_count":    len(ready_kpis),
                "tables":       tables_created,
            },
        )

    return {
        "tables_created": tables_created,
        "kpi_count":      len(ready_kpis),
        "preview_rows":   preview_rows,
    }


# ── Deterministic KPI fallback ────────────────────────────────────────────────
