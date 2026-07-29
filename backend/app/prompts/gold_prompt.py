"""
Prompt builder for Gold layer KPI SQL generation.
The schema_block is always the real live silver schema fetched from information_schema.
No hardcoded table or column names — the model works purely from the provided schema.
Multi-table JOINs are explicitly supported when multiple silver tables are present.
"""


def build_gold_prompt(requirement: str, schema_info: str) -> str:
    if not schema_info.strip():
        raise ValueError(
            "Silver schema is empty — run the Silver layer first before generating Gold KPIs."
        )

    lines = [l.strip() for l in schema_info.strip().splitlines() if l.strip()]
    table_names = [l.split("(")[0].strip() for l in lines if l.startswith("silver.")]
    multi_table = len(table_names) > 1

    if multi_table:
        join_note = (
            f"There are {len(table_names)} tables: {', '.join(table_names)}. "
            "Write JOINs across tables when a KPI needs columns from more than one. "
            "Identify join keys from shared column names (e.g. order_id, customer_id). "
            "Use CTEs (WITH ... AS) when helpful."
        )
    else:
        join_note = "Only one table is available. Query it directly."

    return f"""You are a BI engineer. Write 2 KPI SQL queries for the requirement below.

REQUIREMENT: {requirement}

SILVER SCHEMA (use ONLY these exact names):
{schema_info.strip()}

RULES:
- Valid PostgreSQL SELECT statements only.
- Reference tables as silver.<table_name> exactly as shown.
- {join_note}
- No semicolons at end of SQL.
- If a KPI cannot be computed, set status "Unavailable" and sql "".
- Output ONLY valid JSON, no markdown, no explanation.

OUTPUT:
{{"kpis":[{{"name":"<name>","status":"Ready","sql":"<SELECT ...>"}},{{"name":"<unavailable>","status":"Unavailable","sql":""}}]}}
"""
