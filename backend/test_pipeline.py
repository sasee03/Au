"""
End-to-end pipeline test — Bronze → Silver → Gold
Run:  python test_pipeline.py
"""
import asyncio
import asyncpg

HOST     = "localhost"
PORT     = 5432
DB       = "aurum"
USER     = "postgres"
PASSWORD = "Indium@123"


async def main():
    conn = await asyncpg.connect(host=HOST, port=PORT, database=DB, user=USER, password=PASSWORD)

    print("=" * 60)
    print("AURUM Pipeline Test")
    print("=" * 60)

    # ── 1. Verify bronze table ────────────────────────────────────────────────
    bronze_cnt = await conn.fetchval('SELECT COUNT(*) FROM bronze."test_orders"')
    cols = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='bronze' AND table_name='test_orders' ORDER BY ordinal_position"
    )
    print(f"\n[1] Bronze: bronze.test_orders  →  {bronze_cnt} rows, {len(cols)} cols")
    for c in cols:
        print(f"    {c['column_name']:<20} {c['data_type']}")

    # ── 2. Silver: chain 3 SQL steps as CTEs ─────────────────────────────────
    print("\n[2] Running Silver CTE chain…")

    # step_0: cast invoice_date to timestamp
    # step_1: trim whitespace — explicit SELECT (no SELECT *) to avoid CTE ambiguity
    # step_2: add line_total = quantity * unit_price (::numeric cast — bronze is all TEXT)
    cte_block = """
WITH
step_0 AS (
    SELECT "invoice_no", "stock_code", "quantity", "unit_price", "customer_id",
           "invoice_date"::timestamp AS "invoice_date", "ingested_at", "source_file"
    FROM bronze."test_orders"
),
step_1 AS (
    SELECT "quantity", "unit_price", "invoice_date", "ingested_at", "source_file",
           TRIM("invoice_no") AS "invoice_no",
           TRIM("stock_code") AS "stock_code",
           TRIM("customer_id") AS "customer_id"
    FROM step_0
),
step_2 AS (
    SELECT *,
           "quantity"::numeric * "unit_price"::numeric AS "line_total"
    FROM step_1
)
"""
    # Count
    cnt = await conn.fetchval(f"{cte_block} SELECT COUNT(*) FROM step_2")
    print(f"    Silver rows after CTE chain: {cnt}")

    cte_with_filter = cte_block.rstrip() + """,
step_3 AS (
    SELECT * FROM step_2 WHERE "customer_id" IS NOT NULL
)
"""
    cnt_filtered = await conn.fetchval(f"{cte_with_filter} SELECT COUNT(*) FROM step_3")
    print(f"    After removing NULL customer_id: {cnt_filtered}")

    # Write silver table: CREATE TABLE x AS (WITH ... SELECT *)
    await conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
    await conn.execute('DROP TABLE IF EXISTS silver."test_orders_silver"')
    await conn.execute(
        f'CREATE TABLE silver."test_orders_silver" AS '
        f'({cte_with_filter} SELECT * FROM step_3)'
    )
    silver_cnt = await conn.fetchval('SELECT COUNT(*) FROM silver."test_orders_silver"')
    silver_cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='silver' AND table_name='test_orders_silver' ORDER BY ordinal_position"
    )
    print(f"    Created silver.test_orders_silver  →  {silver_cnt} rows, {len(silver_cols)} cols")
    print(f"    Columns: {', '.join(c['column_name'] for c in silver_cols)}")

    # Preview
    rows = await conn.fetch('SELECT * FROM silver."test_orders_silver" LIMIT 3')
    print(f"\n    Preview:")
    for r in rows:
        print(f"      invoice_no={r['invoice_no']}  qty={r['quantity']}  "
              f"unit_price={r['unit_price']}  line_total={r['line_total']}")

    # ── 3. Gold: aggregate KPI from silver ───────────────────────────────────
    print("\n[3] Running Gold KPI…")
    await conn.execute("CREATE SCHEMA IF NOT EXISTS gold")

    kpi_sql = """
        SELECT
            TRIM("invoice_no") AS invoice,
            SUM("line_total"::numeric) AS total_revenue,
            COUNT(*) AS line_count
        FROM silver."test_orders_silver"
        GROUP BY 1
        ORDER BY 2 DESC
    """
    await conn.execute('DROP TABLE IF EXISTS gold."gold_revenue_by_invoice"')
    await conn.execute(f'CREATE TABLE gold."gold_revenue_by_invoice" AS ({kpi_sql})')
    gold_cnt = await conn.fetchval('SELECT COUNT(*) FROM gold."gold_revenue_by_invoice"')
    print(f"    Created gold.gold_revenue_by_invoice  →  {gold_cnt} rows")

    gold_rows = await conn.fetch('SELECT * FROM gold."gold_revenue_by_invoice"')
    for r in gold_rows:
        print(f"      {r['invoice']}: revenue={r['total_revenue']}  lines={r['line_count']}")

    # ── 4. Final state ────────────────────────────────────────────────────────
    print("\n[4] Final DB state:")
    tables = await conn.fetch("""
        SELECT schemaname, tablename,
               pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
        FROM pg_tables
        WHERE schemaname IN ('bronze','silver','gold')
        ORDER BY schemaname, tablename
    """)
    for t in tables:
        print(f"    {t['schemaname']}.{t['tablename']}  ({t['size']})")

    await conn.close()
    print("\n✓ Full Bronze → Silver → Gold pipeline PASSED\n")


asyncio.run(main())
