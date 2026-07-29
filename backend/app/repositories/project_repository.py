"""
Project repository — all DB operations for the projects table.
"""
from typing import Optional
from app import database as db
from app.models.schemas import ProjectCreate, ProjectOut


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


async def create(data: ProjectCreate) -> dict:
    row = await db.fetchrow(
        """
        INSERT INTO projects (name, domain, description, environment)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        data.name,
        data.domain or "Other",
        data.description or "",
        data.environment or "Development",
    )
    return _row_to_dict(row)


async def list_all(limit: int = 50) -> list[dict]:
    rows = await db.fetch(
        "SELECT * FROM projects ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return [_row_to_dict(r) for r in rows]


async def get_by_id(project_id: str) -> Optional[dict]:
    row = await db.fetchrow(
        "SELECT * FROM projects WHERE project_id = $1",
        project_id,
    )
    return _row_to_dict(row) if row else None


async def update_status(project_id: str, status: str):
    await db.execute(
        "UPDATE projects SET status=$1, updated_at=NOW() WHERE project_id=$2",
        status,
        project_id,
    )


async def save_run(
    project_id: str,
    source: str,
    stage: str,
    status: str,
    rows_in: int,
    rows_out: int,
    details: dict,
):
    import json
    await db.execute(
        """
        INSERT INTO pipeline_runs
            (project_id, source, stage, status, rows_in, rows_out, details)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        project_id,
        source,
        stage,
        status,
        rows_in,
        rows_out,
        json.dumps(details),
    )


async def get_runs(project_id: str) -> list[dict]:
    rows = await db.fetch(
        "SELECT * FROM pipeline_runs WHERE project_id=$1 ORDER BY created_at DESC",
        project_id,
    )
    return [_row_to_dict(r) for r in rows]


async def save_cleaning_rules(project_id: str, table_name: str, rules: list, sqls: list):
    for i, (rule, sql) in enumerate(zip(rules, sqls)):
        await db.execute(
            """
            INSERT INTO cleaning_rules
                (project_id, table_name, rule_text, generated_sql, rule_order)
            VALUES ($1,$2,$3,$4,$5)
            """,
            project_id, table_name, rule, sql, i,
        )


async def save_gold_kpis(project_id: str, requirement: str, kpis: list):
    for kpi in kpis:
        await db.execute(
            """
            INSERT INTO gold_kpis (project_id, requirement, kpi_name, kpi_sql, status)
            VALUES ($1,$2,$3,$4,$5)
            """,
            project_id,
            requirement,
            kpi.get("name", ""),
            kpi.get("sql", ""),
            kpi.get("status", "Ready"),
        )
