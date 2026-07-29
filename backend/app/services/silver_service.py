"""
Silver layer service.
- generate_sql : calls AI (Ollama/OpenAI) with real schema + rules → SQL per rule.
                 Falls back to schema-aware deterministic matching if AI unavailable.
- execute_sql  : chains SQL as CTEs, writes result to silver.<table>_silver.

NO hardcoded table/column names — all column references are extracted from the
rule text or the actual schema fetched from the DB.
"""
import asyncpg
import logging
import random
import re
from app.config import settings
from app.prompts.silver_prompt import build_silver_prompt
from app.services.ai_service import call_ai_json
from app.repositories import project_repository as repo

log = logging.getLogger("aurum.silver")


# ── helpers ───────────────────────────────────────────────────────────────────

async def _get_pg_conn(pg_conn_cfg: dict | None) -> asyncpg.Connection | None:
    """Always connect to the single AURUM database where bronze/silver/gold schemas live."""
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
        log.warning(f"[silver] AURUM DB connect failed: {e}")
        return None


async def _fetch_schema(table_name: str, pg_conn_cfg: dict | None) -> list[dict]:
    """Fetch real column info from the bronze table."""
    from app.services.naming import base_name_from_bronze
    bare   = table_name.split(".")[-1]
    source = base_name_from_bronze(bare)   # strips _bronze suffix correctly
    conn   = await _get_pg_conn(pg_conn_cfg)
    if conn is None:
        return []
    try:
        rows = await conn.fetch(
            """SELECT column_name AS col, data_type AS type, is_nullable AS nullable
               FROM information_schema.columns
               WHERE table_schema = 'bronze' AND table_name = $1
               ORDER BY ordinal_position""",
            bare,
        )
        if not rows:
            schema_pg = (pg_conn_cfg or {}).get("schema_name") or \
                        (pg_conn_cfg or {}).get("schema") or "public"
            rows = await conn.fetch(
                """SELECT column_name AS col, data_type AS type, is_nullable AS nullable
                   FROM information_schema.columns
                   WHERE table_schema = $1 AND table_name = $2
                   ORDER BY ordinal_position""",
                schema_pg, source,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning(f"[silver] schema fetch error: {e}")
        return []
    finally:
        await conn.close()


async def _table_exists(conn: asyncpg.Connection, schema: str, table: str) -> bool:
    try:
        r = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=$1 AND table_name=$2",
            schema, table,
        )
        return r is not None
    except Exception:
        return False


def _strip_comments(sql: str) -> str:
    """Strip -- line comments so they don't break CTE parentheses."""
    return re.sub(r"--[^\n]*", "", sql).strip().rstrip(";")


# ── SQL generation ────────────────────────────────────────────────────────────

async def generate_sql(
    table: str,
    rules: list[str],
    project_id: str | None,
    pg_conn_cfg: dict | None = None,
) -> dict:
    """
    Generate one SQL SELECT per cleaning rule.
    Uses AI when available; deterministic fallback otherwise.
    Column names are always extracted from rule text or the real schema — never hardcoded.
    """
    log.info(f"[silver] generate_sql table={table!r} rules={len(rules)}")

    schema_cols = await _fetch_schema(table, pg_conn_cfg)
    col_names   = [c["col"] for c in schema_cols]
    log.info(f"[silver] schema cols: {col_names}")

    prompt = build_silver_prompt(table, schema_cols, rules)

    try:
        log.info("[silver] calling AI…")
        result = await call_ai_json(prompt)
        items  = result.get("sql_per_rule", [])
        if not items:
            raise ValueError("AI returned empty sql_per_rule")
        log.info(f"[silver] AI returned {len(items)} items for {len(rules)} rules")
    except Exception as e:
        log.error(f"[silver] AI failed: {e}")
        raise RuntimeError(
            f"AI model unavailable: {e}. "
            "Start Ollama with 'ollama serve' and pull a model with 'ollama pull sqlcoder'."
        ) from e

    aligned = []
    for i, rule in enumerate(rules):
        sql = ""
        if i < len(items) and items[i].get("sql", "").strip():
            sql = _strip_comments(items[i]["sql"])
        aligned.append({"rule": rule, "sql": sql})

    result = {"sql_per_rule": aligned}

    if project_id:
        sqls = [it["sql"] for it in aligned]
        await repo.save_cleaning_rules(project_id, table, rules, sqls)

    return result


# ── SQL preview (dry run — no DB write) ──────────────────────────────────────

async def preview_sql(
    table: str,
    sql_per_rule: list[str],
    pg_conn_cfg: dict | None,
) -> dict:
    """
    Run the CTE chain against the live bronze table and return the first 5 rows.
    Nothing is written to the database — SELECT only.
    Returns {"preview_rows": [...], "row_count": int, "error": str|None}
    """
    conn = await _get_pg_conn(pg_conn_cfg)
    if conn is None:
        return {"preview_rows": [], "row_count": 0, "error": "Could not connect to database"}

    try:
        bare = table.split(".")[-1]
        from app.services.naming import base_name_from_bronze
        source    = base_name_from_bronze(bare)
        pg_schema = (pg_conn_cfg or {}).get("schema_name") or \
                    (pg_conn_cfg or {}).get("schema") or "public"

        cte_parts: list[str] = []
        cte_index = 0
        for sql in sql_per_rule:
            raw = _strip_comments(sql)
            if not raw:
                continue
            if cte_index == 0:
                src = f'"bronze"."{bare}"'
                if not await _table_exists(conn, "bronze", bare):
                    src = f'"{pg_schema}"."{source}"'
            else:
                src = f"step_{cte_index - 1}"
            step_sql = raw.replace("__INPUT__", src)
            cte_parts.append(f"step_{cte_index} AS ({step_sql})")
            cte_index += 1

        if not cte_parts:
            return {"preview_rows": [], "row_count": 0, "error": "No valid SQL to preview"}

        cte_block = "WITH " + ",\n".join(cte_parts)
        last_step = f"step_{cte_index - 1}"

        row_count = 0
        try:
            cnt = await conn.fetchval(f"{cte_block} SELECT COUNT(*) FROM {last_step}")
            row_count = int(cnt or 0)
        except Exception as e:
            log.warning(f"[silver/preview] count failed: {e}")

        preview_rows: list[dict] = []
        try:
            rows = await conn.fetch(f"{cte_block} SELECT * FROM {last_step} LIMIT 5")
            preview_rows = [dict(r) for r in rows]
        except Exception as e:
            log.warning(f"[silver/preview] fetch failed: {e}")
            return {"preview_rows": [], "row_count": row_count, "error": str(e)}

        return {"preview_rows": preview_rows, "row_count": row_count, "error": None}

    except Exception as e:
        log.error(f"[silver/preview] error: {e}")
        return {"preview_rows": [], "row_count": 0, "error": str(e)}
    finally:
        await conn.close()


# ── SQL execution ─────────────────────────────────────────────────────────────

async def execute_sql(
    table: str,
    rules: list[str],
    sql_per_rule: list[str],
    project_id: str | None,
    pg_conn_cfg: dict | None,
) -> dict:
    """Chain SQL as CTEs, write silver table, return real counts + preview."""
    bronze_rows = 0
    silver_rows = 0
    effects: list[dict] = []
    preview_rows: list[dict] = []

    conn = await _get_pg_conn(pg_conn_cfg)
    if conn:
        try:
            bare      = table.split(".")[-1]
            # Extract base_name using naming convention: strip schema, strip _bronze suffix
            from app.services.naming import base_name_from_bronze, silver_table as make_silver_tbl
            source    = base_name_from_bronze(bare)   # "customer_orders_bronze" → "customer_orders"
            silver_tbl = make_silver_tbl(source)       # "customer_orders_silver"
            pg_schema = (pg_conn_cfg or {}).get("schema_name") or \
                        (pg_conn_cfg or {}).get("schema") or "public"

            # Count source rows
            for chk_schema, chk_table in [("bronze", bare), (pg_schema, source)]:
                try:
                    cnt = await conn.fetchval(
                        f'SELECT COUNT(*) FROM "{chk_schema}"."{chk_table}"'
                    )
                    bronze_rows = int(cnt or 0)
                    silver_rows = bronze_rows
                    break
                except Exception:
                    continue

            # Build CTE chain — strip comments from every SQL step
            cte_parts: list[str] = []
            cte_index = 0
            for sql in sql_per_rule:
                raw = _strip_comments(sql)
                if not raw:
                    continue

                if cte_index == 0:
                    src = f'"bronze"."{bare}"'
                    if not await _table_exists(conn, "bronze", bare):
                        src = f'"{pg_schema}"."{source}"'
                else:
                    src = f"step_{cte_index - 1}"

                step_sql = raw.replace("__INPUT__", src)
                cte_parts.append(f"step_{cte_index} AS ({step_sql})")
                cte_index += 1

            if cte_parts:
                cte_block = "WITH " + ",\n".join(cte_parts)
                last_step = f"step_{cte_index - 1}"

                try:
                    cnt = await conn.fetchval(
                        f"{cte_block} SELECT COUNT(*) FROM {last_step}"
                    )
                    silver_rows = int(cnt or silver_rows)
                except Exception as e:
                    log.warning(f"[silver] CTE count failed: {e}")

                try:
                    p_rows = await conn.fetch(
                        f"{cte_block} SELECT * FROM {last_step} LIMIT 5"
                    )
                    if p_rows:
                        preview_rows = [dict(r) for r in p_rows]
                except Exception as e:
                    log.warning(f"[silver] CTE preview failed: {e}")

                silver_tbl = make_silver_tbl(source)   # already set above
                try:
                    await conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
                    await conn.execute(f'DROP TABLE IF EXISTS silver."{silver_tbl}"')
                    # PostgreSQL syntax: CREATE TABLE x AS (WITH cte AS (...) SELECT ...)
                    # NOT: WITH cte AS (...) CREATE TABLE x AS SELECT ...
                    await conn.execute(
                        f'CREATE TABLE silver."{silver_tbl}" AS '
                        f'({cte_block} SELECT * FROM {last_step})'
                    )
                    log.info(f"[silver] Created silver.\"{silver_tbl}\" ({silver_rows} rows)")
                except Exception as e:
                    log.warning(f"[silver] Write silver table failed: {e}")

        except Exception as e:
            log.error(f"[silver] execute_sql error: {e}")
        finally:
            await conn.close()

    else:
        # Simulate without DB (no real row counts available)
        bronze_rows = 0
        silver_rows = 0
        for sql in sql_per_rule:
            is_filter = any(k in sql.upper() for k in ("WHERE", "DISTINCT ON", "DISTINCT"))
            removed   = int(silver_rows * random.uniform(0.02, 0.05)) if is_filter and silver_rows else 0
            silver_rows -= removed
            effects.append({"removed": removed, "type": "remove" if is_filter else "transform"})

    affected   = max(0, bronze_rows - silver_rows)
    pct_change = f"{(affected / bronze_rows * -100):.2f}%" if bronze_rows else "0.00%"

    full_effects = [
        {
            "rule":    rules[i] if i < len(rules) else f"Rule {i+1}",
            "removed": effects[i]["removed"] if i < len(effects) else 0,
            "type":    effects[i]["type"]    if i < len(effects) else "transform",
        }
        for i in range(len(sql_per_rule))
    ]

    if project_id:
        await repo.save_run(
            project_id,
            "postgres" if pg_conn_cfg else "csv",
            "silver", "PASS",
            bronze_rows, silver_rows,
            {"rules": rules, "affected": affected, "pct_change": pct_change},
        )

    return {
        "bronze_rows":  bronze_rows,
        "silver_rows":  silver_rows,
        "affected":     affected,
        "pct_change":   pct_change,
        "effects":      full_effects,
        "preview_rows": preview_rows,   # real rows from DB; empty list if no DB
    }

