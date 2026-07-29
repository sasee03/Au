# AURUM Platform — Complete Developer Guide

## Overview
AURUM is a data validation & quality platform with three medallion layers: **Bronze** (raw ingestion), **Silver** (cleaning/validation), **Gold** (business KPIs). Built with FastAPI (backend) + React (frontend), backed by PostgreSQL.

---

## Folder Structure & Architecture

### Root Level
```
D:\Au\
├── backend/               # FastAPI server
├── frontend/              # React + Vite SPA
└── PLATFORM_GUIDE.md      # This file
```

### Backend (`backend/`)
```
backend/
├── main.py                # FastAPI app entry point
├── requirements.txt       # Python dependencies
├── .env                   # DB credentials (not in git)
├── AURUM.md              # Backend development notes
│
├── app/
│   ├── __init__.py
│   ├── config.py         # Environment & settings
│   ├── database.py       # PostgreSQL connection pool
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py    # Pydantic models for all API contracts
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── gold_prompt.py    # AI prompt for KPI generation
│   │   ├── silver_prompt.py  # AI prompt for SQL generation
│   │   └── bronze_prompt.py  # (future) Bronze validation rules
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── project_repository.py  # Database queries for projects/runs
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── naming.py              # TABLE NAMING CONVENTION (core!)
│   │   ├── bronze_service.py      # CSV/Postgres ingest, preview
│   │   ├── silver_service.py      # SQL generation & execution
│   │   ├── gold_service.py        # KPI generation & execution
│   │   ├── ai_service.py          # OpenAI API wrapper
│   │   └── [bronze|silver|gold]_service.py  # Layer-specific logic
│   │
│   └── routes/
│       ├── __init__.py
│       ├── postgres.py    # POST /api/postgres/* → DB introspection
│       ├── bronze.py      # POST /api/bronze/* → upload, list, preview
│       ├── silver.py      # POST /api/silver/* → generate-sql, execute
│       ├── gold.py        # POST /api/gold/* → generate-kpi, execute
│       ├── projects.py    # POST /api/projects/* → project CRUD
│       ├── docs.py        # GET /api/docs → API documentation
│       └── report.py      # GET /api/report/* → final results
```

### Frontend (`frontend/`)
```
frontend/
├── package.json          # React + Vite + dependencies
├── vite.config.js        # Vite build config
├── index.html            # Entry point
│
├── src/
│   ├── main.jsx          # React DOM render
│   ├── App.jsx           # Router setup
│   ├── index.css         # Global styles
│   │
│   ├── components/
│   │   ├── Sidebar.jsx           # Unified sidebar (all pages)
│   │   └── TopNav.jsx            # Common top navigation
│   │
│   └── pages/
│       ├── HomePage.jsx                   # / → project list
│       ├── NewProjectPage.jsx             # /new → create project
│       ├── DataConnectorsPage.jsx         # /project/:id/connect → upload CSV or connect Postgres
│       ├── DatasetExplorerPage.jsx        # /project/:id/select → browse & select tables
│       ├── PipelineConfigPage.jsx         # /project/:id/pipeline-config → choose tables
│       ├── BronzeLayerPage.jsx            # /project/:id/bronze → raw data preview
│       ├── SilverValidationPage.jsx       # /project/:id/silver → write cleaning rules
│       ├── GoldLayerPage.jsx              # /project/:id/gold → define KPIs
│       └── ReportPage.jsx                 # /project/:id/report → final results
```

---

## Table Naming Convention (CRITICAL)

This is standardized across all three layers. Given filename `customer_orders.csv`:

```python
# From naming.py:
base_name = "customer_orders"  # stem, lowercased, safe chars only

# Bronze layer:
bronze."customer_orders_bronze"

# Silver layer:
silver."customer_orders_silver"

# Gold layer (per KPI):
gold."customer_orders_gold_total_revenue"
gold."customer_orders_gold_sales_by_state"
```

**Implementation:** `backend/app/services/naming.py` exports:
- `make_base_name(raw: str) → str` — convert any filename/table name to safe base_name
- `bronze_table(base_name: str) → str` — returns `{base_name}_bronze`
- `silver_table(base_name: str) → str` — returns `{base_name}_silver`
- `gold_table(base_name: str, kpi_name: str) → str` — returns `{base_name}_gold_{kpi_slug}`
- `base_name_from_bronze(bronze_tbl: str) → str` — extract base_name from bronze table name

**All services import and use these functions** — never construct table names manually.

---

## SessionStorage Keys (Frontend)

Frontend uses `sessionStorage` to pass data through the SPA (no backend session needed).

| Key | Type | Set By | Used By |
|---|---|---|---|
| `aurum_project_id` | string | NewProjectPage | All pages (for project context) |
| `aurum_source` | "csv" or "postgres" | DataConnectorsPage | BronzeLayerPage, SilverValidationPage |
| `aurum_dataset` | string | DataConnectorsPage (CSV filename stem) | BronzeLayerPage, SilverValidationPage |
| `aurum_base_name` | string | DataConnectorsPage (from /bronze/upload response) | SilverValidationPage, GoldLayerPage |
| `aurum_pg_conn` | JSON stringified | DataConnectorsPage | DatasetExplorerPage, BronzeLayerPage |
| `aurum_selected_tables` | JSON array | DatasetExplorerPage, PipelineConfigPage | BronzeLayerPage (used for schema context) |
| `aurum_bronze_table` | "bronze.{table_name}" | BronzeLayerPage (from /bronze/preview) | SilverValidationPage (table label) |
| `aurum_bronze_schema` | JSON array of columns | BronzeLayerPage (from /bronze/preview) | SilverValidationPage (fallback SQL builder) |
| `aurum_silver_result` | JSON object | SilverValidationPage (after /silver/execute) | ReportPage (display results) |
| `aurum_gold_result` | JSON object | GoldLayerPage (after /gold/execute) | ReportPage (display results) |

---

## Data Flow: The Three Medallion Layers

### LAYER 1: BRONZE (Raw Ingestion)
**Goal:** Ingest data exactly as-is, add metadata (ingested_at, source_file), store in bronze schema.

**Endpoints:**
- `POST /api/bronze/upload` → handles CSV upload
- `POST /api/bronze/ingest` → ingests Postgres tables
- `GET /api/bronze/list` → list all bronze tables
- `GET /api/bronze/preview?table=X` → fetch first 50 rows + schema

**Data Path:**
1. User uploads CSV via **DataConnectorsPage** → `POST /api/bronze/upload`
2. **bronze_service.ingest_csv()** processes:
   - `base_name = make_base_name(filename)` (e.g., "customer_orders")
   - Create table: `bronze."{base_name}_bronze"`
   - Write all rows with metadata columns (ingested_at, source_file)
3. Returns: `{bronze_table, base_name, row_count, schema_cols}`
4. **DataConnectorsPage** stores in sessionStorage:
   - `aurum_bronze_table = "bronze.customer_orders_bronze"`
   - `aurum_base_name = "customer_orders"`
5. User navigates to **BronzeLayerPage** → fetches preview via `GET /api/bronze/preview`
6. Preview displays rows + column schema

---

### LAYER 2: SILVER (Cleaning & Validation)
**Goal:** User defines cleaning rules → AI generates SQL → execute to create clean silver table.

**Endpoints:**
- `POST /api/silver/generate-sql` → AI writes SQL for each rule
- `POST /api/silver/execute` → run the SQL pipeline, create silver.{base_name}_silver

**Data Path:**
1. **SilverValidationPage** loads with `aurum_bronze_table` in state
2. User enters cleaning rules (e.g., "remove duplicates", "trim whitespace")
3. Click "Generate SQL" → `POST /api/silver/generate-sql`:
   - Input: rules + bronze table name + schema info
   - **ai_service** calls OpenAI with prompt from **silver_prompt.py**
   - Returns SQL per rule (or fallback client-side SQL if AI unavailable)
4. User can edit SQL or accept generated
5. Click "Approve & Execute" → `POST /api/silver/execute`:
   - **silver_service.execute_sql()** chains SQL as CTEs:
     ```sql
     WITH step_0 AS (SELECT ... FROM bronze.customer_orders_bronze),
          step_1 AS (SELECT ... FROM step_0),
          ...
     SELECT * INTO silver.customer_orders_silver FROM step_n
     ```
   - Returns: bronze row count, silver row count, affected rows, preview rows
6. Stores result in sessionStorage: `aurum_silver_result`
7. Navigates to **GoldLayerPage**

---

### LAYER 3: GOLD (Business KPIs)
**Goal:** User defines business requirement → AI generates KPI SQL → execute to create gold tables.

**Endpoints:**
- `POST /api/gold/generate-kpi` → AI decomposes requirement into KPIs + SQL
- `POST /api/gold/execute` → run each KPI's SQL, create gold.{base_name}_gold_{kpi} tables

**Data Path:**
1. **GoldLayerPage** loads with `aurum_base_name` in state
2. User enters requirement (e.g., "I need total revenue by country and top 10 customers")
3. Click "Generate KPIs" → `POST /api/gold/generate-kpi`:
   - Input: requirement + silver schema info
   - **ai_service** calls OpenAI with prompt from **gold_prompt.py**
   - Returns list of KPIs: `[{name: "Total Revenue", sql: "SELECT ..."}]`
4. User can edit KPI SQL or accept generated
5. Click "Approve & Build" → `POST /api/gold/execute`:
   - **gold_service.execute_gold()** for each KPI:
     ```sql
     CREATE TABLE gold.customer_orders_gold_total_revenue AS (SELECT ...)
     CREATE TABLE gold.customer_orders_gold_sales_by_country AS (SELECT ...)
     ...
     ```
   - Returns: tables_created, preview_rows
6. Stores result in sessionStorage: `aurum_gold_result`
7. Navigates to **ReportPage**

---

## Backend API Reference

All endpoints POST to `/api/{service}/{action}` and return JSON.

### Postgres Introspection (`POST /api/postgres/*`)
| Endpoint | Input | Output | Purpose |
|---|---|---|---|
| `/test` | PgConnConfig | `{ok: bool, error?: str}` | Test connection |
| `/tables` | PgConnConfig | `[{name, rows, cols, size}]` | List tables in schema |
| `/schemas` | PgConnConfig | `[schema_name]` | List all schemas |
| `/tree` | PgConnConfig | `[{schema, tables: [name]}]` | Full schema tree |
| `/schema` | PgConnConfig + table | `[{col, type, nullable}]` | Columns for one table |

**PgConnConfig Schema:**
```python
{
  "host": str,
  "port": int,
  "database": str,
  "username": str,
  "password": str,
  "schema_name": str,
  "ssl": bool
}
```

### Bronze Layer (`POST /api/bronze/*`)
| Endpoint | Input | Output | Purpose |
|---|---|---|---|
| `/upload` | FormData (file, dataset_name, delimiter, encoding) | `{bronze_table, base_name, row_count, col_count, schema_cols, sample_rows}` | Upload CSV |
| `/ingest` | `{source, tables, pg_conn, project_id}` | `{ok, result: []}` | Ingest Postgres tables |
| `/list` | — | `[table_name]` | List all bronze tables |
| `/preview` | `?table=X` | `{rows, schema_cols, row_count, col_count, bronze_table}` | Get table preview |

### Silver Layer (`POST /api/silver/*`)
| Endpoint | Input | Output | Purpose |
|---|---|---|---|
| `/generate-sql` | `{table, rules, project_id, pg_conn}` | `{sql_per_rule: [{rule, sql}]}` | AI generates SQL |
| `/execute` | `{table, rules, sql_per_rule, project_id, pg_conn}` | `{bronze_rows, silver_rows, affected, pct_change, preview_rows}` | Execute & create table |

### Gold Layer (`POST /api/gold/*`)
| Endpoint | Input | Output | Purpose |
|---|---|---|---|
| `/generate-kpi` | `{requirement, schema_info, project_id, pg_conn}` | `{kpis: [{name, sql, status}]}` | AI decomposes requirement |
| `/execute` | `{kpis, requirement, project_id, pg_conn}` | `{tables_created, preview_rows}` | Execute & create tables |

---

## Frontend Pages & Workflow

### Page: DataConnectorsPage (`/project/:id/connect`)
- **Purpose:** Let user choose upload CSV or connect Postgres
- **Inputs:** projectId from URL
- **Outputs to sessionStorage:**
  - `aurum_source` (csv or postgres)
  - `aurum_dataset` (filename stem for CSV, or empty)
  - `aurum_bronze_table` (from /upload response)
  - `aurum_base_name` (from /upload response)
  - `aurum_pg_conn` (connection details)
- **Stores:** `bronze.{base_name}_bronze` is now available
- **Navigation:** Continue → `/project/:id/select` (Postgres) or `/project/:id/bronze` (CSV)

### Page: DatasetExplorerPage (`/project/:id/select`)
- **Purpose:** Browse schema tree, select tables to ingest
- **Shows:** Real schema tree from `GET /api/postgres/tree`
- **Outputs to sessionStorage:**
  - `aurum_selected_tables` (JSON array of chosen table names)
- **Navigation:** Continue → `/project/:id/pipeline-config`

### Page: PipelineConfigPage (`/project/:id/pipeline-config`)
- **Purpose:** Confirm table selection & create pipeline run
- **Inputs:** aurum_selected_tables from sessionStorage
- **Creates:** Pipeline run record in DB
- **Navigation:** Continue → `/project/:id/bronze`

### Page: BronzeLayerPage (`/project/:id/bronze`)
- **Purpose:** View raw bronze data, confirm ingestion
- **Fetches:** `GET /api/bronze/list` → shows all bronze tables
- **Shows:** Table picker (dropdown if multiple tables), raw rows + schema
- **Stores:**
  - `aurum_bronze_table` (from preview response)
  - `aurum_bronze_schema` (column definitions for Silver page fallback)
- **Navigation:** Continue → `/project/:id/silver`

### Page: SilverValidationPage (`/project/:id/silver`)
- **Purpose:** Define cleaning rules, generate SQL, execute
- **Inputs:** aurum_bronze_table, aurum_base_name, aurum_bronze_schema
- **Flow:**
  1. User enters rules (text) — one rule per row
  2. Click "Generate SQL" → AI writes SQL, or fallback client-side SQL builder
  3. User can edit SQL inline
  4. Click "Approve & Execute" → runs SQL pipeline, creates `silver.{base_name}_silver`
- **Stores:** `aurum_silver_result` (counts + preview)
- **Navigation:** Continue → `/project/:id/gold`

### Page: GoldLayerPage (`/project/:id/gold`)
- **Purpose:** Define KPIs, generate SQL, execute
- **Inputs:** aurum_silver_result (schema info), aurum_base_name
- **Flow:**
  1. User enters business requirement (textarea)
  2. Click "Generate KPIs" → AI decomposes into KPI list + SQL
  3. User can edit KPI SQL inline, select "Ready" status
  4. Click "Approve & Build" → executes each KPI, creates gold tables
- **Stores:** `aurum_gold_result` (tables_created + preview)
- **Navigation:** Continue → `/project/:id/report`

### Page: ReportPage (`/project/:id/report`)
- **Purpose:** Display final results from Bronze, Silver, Gold
- **Inputs:** sessionStorage keys for all results
- **Shows:**
  - Bronze stats (row count, columns)
  - Silver stats (rows removed, % change)
  - Gold tables (KPI results with preview rows)
- **Navigation:** Back to projects

---

## Development Workflow

### Setup
```bash
# Backend
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Run Locally
```bash
# Terminal 1: Backend
cd backend
python main.py
# Listens on http://localhost:4000

# Terminal 2: Frontend
cd frontend
npm run dev
# Listens on http://localhost:5173 (Vite default)
```

### Database
- PostgreSQL required (see `.env` for connection string)
- Two databases needed:
  - **aurum** (local) — stores bronze/silver/gold tables
  - **user's database** (external, optional) — source for Postgres connector

### Build for Production
```bash
cd frontend
npm run build  # Creates dist/ folder

# Backend is ready as-is; deploy with gunicorn/uvicorn
```

---

## Key Files for Next Developer

| File | Why Important |
|---|---|
| `backend/app/services/naming.py` | Core naming convention — ALL table names flow through here |
| `backend/app/services/bronze_service.py` | CSV upload + Postgres ingestion logic |
| `backend/app/services/silver_service.py` | SQL generation + CTE execution pipeline |
| `backend/app/services/gold_service.py` | KPI generation + multi-table execution |
| `backend/app/prompts/silver_prompt.py` | Prompt that drives SQL generation — tune for better SQL |
| `backend/app/prompts/gold_prompt.py` | Prompt that drives KPI decomposition — tune for business KPIs |
| `frontend/src/pages/SilverValidationPage.jsx` | Heart of data cleaning — where rules turn into SQL |
| `frontend/src/pages/GoldLayerPage.jsx` | Heart of KPI generation — where requirements turn into tables |
| `PLATFORM_GUIDE.md` | This file — keep updated as the codebase evolves |

---

## Common Tasks for Next Developer

### Add a new cleaning rule type to Silver
1. Edit `backend/app/prompts/silver_prompt.py` to include the rule type
2. Edit `frontend/src/pages/SilverValidationPage.jsx` buildFallbackSQL() to handle the rule client-side
3. Test with AI and without (fallback path)

### Add a new KPI to Gold
1. Edit `backend/app/prompts/gold_prompt.py` to suggest the KPI for certain requirements
2. Test by entering a requirement that should trigger it

### Change table naming convention
1. Update functions in `backend/app/services/naming.py`
2. Update all three service files (bronze, silver, gold) to use new functions
3. NO manual string concatenation — always use naming.py functions

### Debug why a table isn't showing up
1. Check sessionStorage keys (open browser DevTools → Application → Session Storage)
2. Check backend logs for "bronze", "silver", or "gold" log statements
3. Query the aurum database directly: `SELECT * FROM information_schema.tables WHERE table_schema IN ('bronze', 'silver', 'gold')`

---

## Notes & Future Work

- **AI Fallback:** If OpenAI is unreachable, the platform gracefully uses client-side SQL builders
- **Multi-table Support:** Currently processes one dataset at a time; could extend for joins
- **Real-time Validation:** Could add row-level data quality checks during Silver execution
- **Incremental Runs:** Pipeline currently full reload; could optimize for changed rows only
- **Export:** Gold tables can be exported to CSV/Excel/BI tools via report page

