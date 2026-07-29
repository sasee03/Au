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

### 9. Report (`/project/:id/report`)
- Full pipeline summary: Ingestion → Bronze → Silver → Gold
- Row counts, transformation effects, data quality score
- Gold layer preview data
- Export as PDF

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
