"""
All Pydantic request/response schemas for AURUM.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    domain: Optional[str] = "Other"
    description: Optional[str] = ""
    environment: Optional[str] = "Development"


class ProjectOut(BaseModel):
    project_id: UUID
    name: str
    domain: Optional[str]
    description: Optional[str]
    environment: Optional[str]
    status: Optional[str] = "PASS"
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

# ── PostgreSQL connection ─────────────────────────────────────────────────────

class PgConnConfig(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str
    schema_name: str = Field("public", alias="schema")
    username: str = "postgres"
    password: str = ""
    ssl: bool = False

    class Config:
        populate_by_name = True


class PgTableInfo(BaseModel):
    name: str
    owner: Optional[str] = "—"
    rows: Optional[str] = "—"
    cols: Optional[int] = 0
    size: Optional[str] = "—"


class PgConnTestResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    tables: Optional[List[PgTableInfo]] = None


# ── Bronze ────────────────────────────────────────────────────────────────────

class BronzeIngestRequest(BaseModel):
    project_id: Optional[str] = None
    tables: List[str] = []
    source: str = "csv"                       # "csv" | "postgres"
    pg_conn: Optional[PgConnConfig] = None


class BronzePreviewResponse(BaseModel):
    rows: List[Dict[str, Any]] = []
    schema_cols: List[Dict[str, Any]] = []
    row_count: int = 0
    col_count: int = 0


# ── Silver ────────────────────────────────────────────────────────────────────

class SqlPerRule(BaseModel):
    rule: str
    sql: str


class SilverGenerateRequest(BaseModel):
    table: str
    rules: List[str]
    project_id: Optional[str] = None
    pg_conn: Optional[PgConnConfig] = None   # pass so service can fetch real schema


class SilverGenerateResponse(BaseModel):
    sql_per_rule: List[SqlPerRule]


class SilverPreviewRequest(BaseModel):
    table: str
    rules: List[str]
    sql_per_rule: List[str]           # ordered list of SQL strings (dry run, no write)
    project_id: Optional[str] = None
    pg_conn: Optional[PgConnConfig] = None


class SilverExecuteRequest(BaseModel):
    table: str
    rules: List[str]
    sql_per_rule: List[str]           # ordered list of SQL strings
    project_id: Optional[str] = None
    pg_conn: Optional[PgConnConfig] = None


class TransformEffect(BaseModel):
    rule: str
    removed: int
    type: str                         # "remove" | "transform"


class SilverExecuteResponse(BaseModel):
    bronze_rows: int
    silver_rows: int
    affected: int
    pct_change: str
    effects: List[TransformEffect]
    preview_rows: List[Dict[str, Any]]


# ── Gold ──────────────────────────────────────────────────────────────────────

class KpiItem(BaseModel):
    name: str
    status: str = "Ready"
    sql: str = ""


class GoldGenerateRequest(BaseModel):
    requirement: str
    project_id: Optional[str] = None
    schema_info: Optional[str] = ""
    pg_conn: Optional[PgConnConfig] = None   # used to fetch live silver schema


class GoldGenerateResponse(BaseModel):
    kpis: List[KpiItem]


class GoldKpiExecute(BaseModel):
    name: str
    sql: str


class GoldExecuteRequest(BaseModel):
    project_id: Optional[str] = None
    requirement: str
    base_name: Optional[str] = None   # e.g. "customer_orders" — drives gold table naming
    kpis: List[GoldKpiExecute]
    pg_conn: Optional[PgConnConfig] = None


class GoldExecuteResponse(BaseModel):
    tables_created: List[str]
    kpi_count: int
    preview_rows: List[Dict[str, Any]]


# ── Report ────────────────────────────────────────────────────────────────────

class PipelineStage(BaseModel):
    stage: str
    icon: str
    status: str
    color: str
    rows_in: str
    rows_out: str
    columns: int
    notes: str
    details: List[str]
    pct_change: Optional[str] = None
    rows_removed: Optional[int] = None
    sql_count: Optional[int] = None
    tables_created: Optional[List[str]] = None
    kpi_count: Optional[int] = None


class ReportSummary(BaseModel):
    total_rows_ingested: str
    final_silver_rows: str
    rows_cleaned: str
    cleaning_rules: int
    kpis_generated: int
    gold_tables: int
    data_quality_score: str
    pipeline_duration: str


class ReportResponse(BaseModel):
    project_name: str
    created_at: str
    source: str
    tables: List[str]
    stages: List[PipelineStage]
    summary: ReportSummary
    gold_preview: List[Dict[str, Any]]
