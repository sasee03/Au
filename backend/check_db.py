import asyncio, asyncpg

async def check():
    conn = await asyncpg.connect(
        host="localhost", port=5432, database="aurum",
        user="postgres", password="Indium@123"
    )
    tables = await conn.fetch("""
        SELECT schemaname, tablename,
               pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
        FROM pg_tables
        WHERE schemaname IN ('bronze','silver','gold')
        ORDER BY schemaname, tablename
    """)
    print(f"Tables in bronze/silver/gold schemas: {len(tables)}")
    for t in tables:
        print(f"  {t['schemaname']}.{t['tablename']}  ({t['size']})")
    if not tables:
        print("  (none yet — upload a CSV or ingest from Postgres first)")

    # Check metadata
    projects = await conn.fetchval("SELECT COUNT(*) FROM projects")
    runs     = await conn.fetchval("SELECT COUNT(*) FROM pipeline_runs")
    print(f"\nMetadata: {projects} projects, {runs} pipeline runs")
    await conn.close()

asyncio.run(check())
