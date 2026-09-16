# AURUM — Enterprise Data Quality Operating System

**Autonomous End-to-End Data Correctness & Business Trust Engine**

---

## What is AURUM?

AURUM is an enterprise-grade data quality platform that automates the entire data pipeline lifecycle — from raw ingestion through cleaning, transformation, KPI generation, and reporting. It follows the **Medallion Architecture** (Bronze → Silver → Gold) and combines deterministic data engineering with AI-powered SQL generation.

---

## Core Architecture

### Medallion Pipeline

```
Source Data  →  Bronze Layer  →  Silver Layer  →  Gold Layer  →  Report
(CSV / PG)       (raw copy)       (cleaned)         (KPIs)       (summary)
```

| Layer  | Database         | Purpose                                                  |
|--------|-----------------|----------------------------------------------------------|
| Bronze | bronze_database  | Exact raw copy. No transformations. Adds metadata cols.  |
| Silver | silver_database  | Cleaned, typed, deduplicated. AI writes the SQL for you. |
| Gold   | gold_database    | Business KPIs aggregated. Dashboard-ready outputs.       |

---

## Key Features

- **Zero-config ingestion** — upload a CSV or connect to any PostgreSQL database
- **AI SQL generation** — describe cleaning rules in plain English; AURUM writes the SQL
- **Editable SQL** — every generated query is shown and editable before execution
- **Approve & Execute model** — nothing runs without your explicit approval
- **KPI auto-discovery** — describe your business goal; AURUM identifies and codes the KPIs
- **Full pipeline report** — one-click report showing every transformation with row counts

---

## Pages & Flow

### 1. Landing Page (`/`)
- Create a new project or open an existing one
- View recent runs with pass/warning/fail status
- Access full documentation

### 2. New Project (`/new-project`)
- Define project name, business domain, description, and environment
- Stored in the AURUM metadata database with a timestamp

### 3. Data Connectors (`/project/:id/connect`)
- **Local CSV** — upload a CSV file; configure delimiter, encoding, header row
- **PostgreSQL** — connect to any Postgres instance including local pgAdmin

### 4. Dataset Explorer (`/project/:id/select`)
- Browse all tables in the connected database
- View row count, column count, and storage size per table
- Select which tables to include in this pipeline run

### 5. Pipeline Configuration (`/project/:id/pipeline-config`)
- Visual overview of what will happen at each layer
- Shows Bronze, Silver, and Gold stage descriptions
- Review execution timeline before committing

### 6. Bronze Layer (`/project/:id/bronze`)
- Displays the raw ingested data exactly as received
- Shows the `information_schema` column reference for Silver rules
- Metadata columns `ingested_at` and `source_file` auto-added
- **Continue to Silver** triggers the actual ingestion

### 7. Silver Validation (`/project/:id/silver`)
- Add cleaning rules in plain English (e.g. *"Remove rows where customer_id is null"*)
- Click **Generate SQL** → AI produces one `SELECT` statement per rule
- Every SQL query is editable directly in the UI
- Click **Approve & Execute** → SQL chain runs, Silver table is created

### 8. Gold Layer (`/project/:id/gold`)
- Enter a business requirement (e.g. *"I need an executive e-commerce dashboard"*)
- Click **Generate KPI Plan** → AI identifies KPIs and writes aggregation SQL
- Review and edit each KPI's SQL
- Click **Approve & Build Gold** → Gold tables created, report triggered

### 7. Bronze Layer (`/project/:id/bronze`)
- **Raw Data Inspection** — Displays the exact ingested tables with no transformations applied
- **Table Tabs** — Click between each selected table to inspect structure and sample rows
- **Information Schema** — Right panel shows column names, detected types, and constraints (e.g., `order_id: VARCHAR`, `order_date: TIMESTAMP`)
- **Row & Column Counts** — Header displays total rows ingested and column count per table
- **Metadata Columns** — Auto-added columns: `ingested_at` (ingestion timestamp), `source_file` (source name), `_bronze_hash` (row hash for deduplication logic)
- **Action** — Click **Continue to Silver** to move to the cleaning phase

---

### 8. Silver Validation (`/project/:id/silver`)
- **Rule Input Box** — Add data cleaning rules in plain English (e.g., "Remove rows where customer_id is null", "Cast order_date to YYYY-MM-DD", "Trim whitespace from all text columns")
- **AI SQL Generation** — Click **Generate SQL** → AURUM sends rules + Bronze schema to the AI → Returns one `SELECT` statement per rule with `WHERE`, `CAST`, or `TRIM` clauses
- **SQL Editor** — View and edit generated SQL directly; highlight errors or optimization opportunities before execution
- **Dry-Run Preview** — Click **Approve** → System runs a `LIMIT 1000` preview showing cleaned data sample and row impact (e.g., "99,000 → 97,000 rows after NULL removal")
- **Execution & Stats** — Click **Execute** → Full transformation runs; cards show rows ingested, rows output, rows removed, and % data loss
- **Multi-Table Workflow** — After executing first table, button changes to "Next: [table_name]"; repeat for each selected table
- **Continue to Gold** — Appears once all tables are executed; moves to KPI generation

---

### 9. Gold Layer (`/project/:id/gold`)
- **Business Requirement Input** — Free-text box asking "What business KPIs do you need?" (e.g., "Executive sales dashboard showing revenue trends, top customers by order value, product performance by category, average delivery time")
- **AI KPI Discovery** — Click **Generate KPI Plan** → AI reads Silver schema, identifies joinable tables, and suggests KPIs with aggregation SQL
- **KPI List** — Left panel shows all discovered KPIs (e.g., "Total Revenue by Month", "Top 10 Customers by Spend", "Average Delivery Duration", "Orders by Status", "Revenue by Customer State")
- **SQL Review & Edit** — Right panel displays SQL for selected KPI; fully editable before execution
- **Join Logic** — AI auto-writes joins across Silver tables (e.g., `orders JOIN order_items ON order_id; JOIN customers ON customer_id`)
- **Dry-Run & Build** — Click **Approve & Build Gold** → Executes all KPI SQL; creates one Gold table per KPI; returns row counts and first 100 rows of each result
- **Gold Preview** — Below KPI list, shows sample data from the first Gold table (first 5 rows, key columns)
- **Action** — Click **Generate Report** to proceed to the final summary

---

### 10. Report (`/project/:id/report`)
- **Pipeline Summary Header** — Project name, domain, environment, run timestamp, and status badge (SUCCESS / WARNING / FAILED)
- **Source Tables** — Lists all tables ingested into Bronze (e.g., olist_orders_dataset, olist_order_items_dataset, olist_customers_dataset)
- **Summary Cards** — Key metrics in grid layout:
  - Total rows ingested into Bronze
  - Total rows in Silver output
  - Rows removed by cleaning rules (count + %)
  - Number of cleaning rules applied
  - Number of KPIs generated
  - Number of Gold tables created
- **Layer Breakdown** — Three sections (Bronze, Silver, Gold) each showing:
  - Layer name and description
  - Table names and row counts
  - Rules or KPIs applied with their descriptions
- **Gold Table Reference** — Exact database table names for BI/dashboard connection (e.g., `gold.olist_orders_revenue_by_month`, `gold.olist_customers_top_10_spend`)
- **Data Quality Score** — Composite score (0–100) based on: null removal rate, duplicate removal rate, type cast success rate
- **Export PDF** — Button at top right; generates professional one-page summary with charts and table references
- **Action** — Click **Back to Projects** or **Create New Pipeline** to start over

---

### 11. Projects Modal (`/projects`)
- **Left Sidebar Link** — Clicking "Projects" from anywhere opens a full-page project list
- **Project Grid** — Each project card shows:
  - Project name (e.g., "Olist Retail")
  - Business domain (e.g., Retail, Finance, Healthcare)
  - Last run timestamp (e.g., "2 days ago")
  - Status badge (PASS / WARNING / FAILED) with color coding (green / yellow / red)
  - Row counts from last run (Bronze → Silver → Gold progression)
- **Actions per Card** — Hover to reveal buttons:
  - **Open** — Re-enter the project pipeline at the Report page
  - **View Report** — Jump directly to the last run's report
  - **Delete** — Remove project and all associated tables (with confirmation dialog)
- **Create New Project** — Button at top right; returns to the New Project wizard
- **Search & Filter** — Search box filters projects by name; domain tabs filter by business category (All / Retail / Finance / etc.)
- **Empty State** — If no projects exist, shows hero message: "No pipelines yet. Click Create New Project to get started."

---

## Backend API

Base URL: `http://localhost:4000/api`

| Method | Endpoint                        | Description                          |
|--------|---------------------------------|--------------------------------------|
| POST   | `/projects`                     | Create a new project                 |
| GET    | `/projects`                     | List all projects                    |
| GET    | `/projects/:id`                 | Get project by ID                    |
| POST   | `/postgres/test`                | Test a PostgreSQL connection         |
| POST   | `/postgres/tables`              | List tables from a connected DB      |
| POST   | `/bronze/upload`                | Upload and parse a CSV file          |
| POST   | `/bronze/ingest`                | Ingest tables from PostgreSQL        |
| GET    | `/bronze/preview`               | Preview bronze table rows            |
| POST   | `/silver/generate-sql`          | AI-generate cleaning SQL per rule    |
| POST   | `/silver/execute`               | Execute Silver transformation chain  |
| POST   | `/gold/generate-kpi`            | AI-generate KPI plan from requirement|
| POST   | `/gold/execute`                 | Execute Gold KPI SQL, create tables  |
| GET    | `/report/:project_id`           | Get full pipeline report             |
| GET    | `/docs`                         | Serve this documentation             |

---

## AI Integration

AURUM supports two AI backends:

### Ollama (local, default)
```
AI_ENDPOINT=http://localhost:11434/api/generate
AI_MODEL=codellama
```
Install Ollama: https://ollama.com  
Pull the model: `ollama pull codellama`

### OpenAI-compatible
```
AI_ENDPOINT=https://api.openai.com/v1/chat/completions
AI_MODEL=gpt-4o
AI_API_KEY=sk-...
```

---

## Data Safety Principles

1. **Append-only Bronze** — raw data is never modified or deleted
2. **No DROP/DELETE in Silver** — only `SELECT` statements are generated
3. **Preview before execute** — every transformation is shown before it runs
4. **Explicit approval** — nothing executes without you clicking Approve
5. **Audit trail** — every run is logged in the metadata database

---

## Running AURUM

### Backend (FastAPI)
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 4000
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

### Database setup
Create the metadata database in PostgreSQL:
```sql
CREATE DATABASE aurum_meta;
```
AURUM will auto-create all tables on first startup.

---

## Environment Variables (backend/.env)

| Variable           | Default                                    | Description                     |
|--------------------|--------------------------------------------|---------------------------------|
| `PORT`             | `4000`                                     | Backend server port             |
| `AURUM_DB_HOST`    | `localhost`                                | Metadata DB host                |
| `AURUM_DB_PORT`    | `5432`                                     | Metadata DB port                |
| `AURUM_DB_NAME`    | `aurum_meta`                               | Metadata DB name                |
| `AURUM_DB_USER`    | `postgres`                                 | Metadata DB user                |
| `AURUM_DB_PASSWORD`| `postgres`                                 | Metadata DB password            |
| `AI_ENDPOINT`      | `http://localhost:11434/api/generate`      | AI model API endpoint           |
| `AI_MODEL`         | `codellama`                                | AI model name                   |
| `AI_API_KEY`       | *(empty)*                                  | API key for OpenAI              |
| `UPLOAD_DIR`       | `./uploads`                                | CSV upload directory            |

---

*AURUM v1.0 — Built for data engineers who care about correctness.*
