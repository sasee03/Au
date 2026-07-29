"""
Prompt builder for Silver layer SQL generation.
Schema is derived directly from the actual bronze table in information_schema
(for CSV: inferred from pandas dtypes; for Postgres: queried live).
No hardcoded column names anywhere.
"""
from typing import List


def build_silver_prompt(
    table_name: str,
    schema_columns: List[dict],
    rules: List[str],
) -> str:
    schema_block = "\n".join(
        f"  {c['col']}  {c.get('type', 'TEXT')}"
        for c in schema_columns
    ) or "  -- schema unavailable"

    col_list = ", ".join(f'"{c["col"]}"' for c in schema_columns)
    rules_block = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))

    return f"""You are an expert SQL data engineer working on a Bronze-to-Silver data pipeline.

Given the exact Bronze table schema and a list of plain-English cleaning rules,
write one SQL SELECT statement per rule.

TABLE: {table_name}

EXACT COLUMN LIST (use only these — do not invent column names):
{schema_block}

CLEANING RULES:
{rules_block}

RULES YOU MUST FOLLOW:
- Write EXACTLY one SELECT per cleaning rule, in the same order as listed.
- Every SELECT must include ALL columns: {col_list}
  Do NOT drop columns that are not being transformed — carry them through unchanged.
- Use __INPUT__ as the FROM source in every SELECT (never the real table name).
- Never use DROP, DELETE, TRUNCATE, INSERT, or UPDATE — only SELECT.
- To remove rows: add a WHERE clause.
- To transform a column: use CAST / UPPER / LOWER / TRIM / COALESCE / INITCAP etc.
- To remove duplicates: use DISTINCT ON ("<col>") ... ORDER BY "<col>".
- To add a derived column: SELECT all existing columns plus the new expression AS new_name.
- Output ONLY valid JSON — no markdown fences, no explanation text, no extra keys.

Required output format:
{{
  "sql_per_rule": [
    {{"rule": "<exact rule text>", "sql": "<complete SELECT statement>"}},
    {{"rule": "<exact rule text>", "sql": "<complete SELECT statement>"}}
  ]
}}
"""
