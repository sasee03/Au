# AURUM Solution Architecture

**Enterprise Data Quality & Pipeline Orchestration Platform**

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Breakdown](#component-breakdown)
4. [Data Flow & Medallion Layers](#data-flow--medallion-layers)
5. [Technology Stack](#technology-stack)
6. [API Architecture](#api-architecture)
7. [Database Design](#database-design)
8. [AI Integration Layer](#ai-integration-layer)
9. [Security & Data Governance](#security--data-governance)
10. [Deployment & Scalability](#deployment--scalability)

---

## System Overview

AURUM is an end-to-end data quality platform that automates the transformation of raw, unstructured data into business-ready KPI tables following the **Medallion Architecture** pattern. The system enables non-technical users to:

- Connect to multiple data sources (CSV, PostgreSQL, Snowflake, Databricks)
- Define data quality and cleaning rules in plain English
- Generate production-grade SQL automatically via AI
- Execute multi-layer transformations with full auditability
- Produce comprehensive pipeline reports with KPI metrics

The platform operates on three core principles:

1. **Deterministic Data Engineering** — Every transformation is explicit, reviewable, and reversible
2. **AI-Powered SQL Generation** — Users describe intent; AI writes the SQL
3. **Explicit Approval Model** — Nothing executes without user consent

---

## Architecture Diagram

**[INSERT ARCHITECTURE DIAGRAM HERE]**

*Diagram shows the complete user journey and data flow from project creation through Bronze/Silver/Gold layers to final reporting.*

---

## Component Breakdown

### Frontend Layer (React + Vite)

**Purpose:** User-facing interface for pipeline orchestration

**Key Components:**

| Component | Path | Function |
|-----------|------|----------|
| **Landing Page** | `src/pages/HomePage.jsx` | Project discovery and creation entry point |
| **New Project Wizard** | `src/pages/NewProjectPage.jsx` | Project metadata capture (name, domain, environment) |
| **Data Connectors** | `src/pages/DataConnectorsPage.jsx` | Connection UI for CSV, PostgreSQL, and cloud data sources |
| **Dataset Explorer** | `src/pages/DatasetExplorerPage.jsx` | Table browser with search, preview, and multi-select |
| **Pipeline Config** | `src/pages/PipelineConfigPage.jsx` | Pre-execution review of medallion layer setup |
| **Bronze Layer** | `src/pages/BronzeLayerPage.jsx` | Raw data inspection and schema reference |
| **Silver Validation** | `src/pages/SilverValidationPage.jsx` | Cleaning rule input, SQL generation, approval, execution |
| **Gold Layer** | `src/pages/GoldLayerPage.jsx` | Business requirement input, KPI discovery, and build |
| **Report** | `src/pages/ReportPage.jsx` | Pipeline summary, metrics, and PDF export |
| **Projects Modal** | `src/pages/ProjectsPage.jsx` | Project grid with status tracking and CRUD |
| **Sidebar** | `src/components/Sidebar.jsx` | Navigation and project context |
| **TopNav** | `src/components/TopNav.jsx` | Breadcrumb and quick actions |

**Tech Stack:** React 18, Vite, Axios, TailwindCSS

---

### Backend Service Layer (FastAPI)

**Purpose:** Business logic, orchestration, and external system integration

**Core Services:**

| Service | Path | Responsibility |
|---------|------|-----------------|
| **AI Service** | `app/services/ai_service.py` | LLM integration (Gemini, Ollama, OpenAI) for SQL/KPI generation |
| **Bronze Service** | `app/services/bronze_service.py` | Raw data ingestion, schema detection, metadata injection |
| **Silver Service** | `app/services/silver_service.py` | Cleaning rule parsing, SQL generation, transformation execution |
| **Gold Service** | `app/services/gold_service.py` | KPI discovery, aggregation SQL generation, KPI materialization |
| **Project Repository** | `app/repositories/project_repository.py` | Project CRUD operations and metadata persistence |

**API Routes:**

| Endpoint | Method | Function |
|----------|--------|----------|
| `/api/projects` | POST/GET | Create or list projects |
| `/api/projects/{id}` | GET | Retrieve project details |
| `/api/postgres/test` | POST | Validate PostgreSQL connection |
| `/api/postgres/tables` | POST | List tables from connected database |
| `/api/bronze/upload` | POST | CSV file upload and parsing |
| `/api/bronze/ingest` | POST | Ingest tables from source system |
| `/api/bronze/preview` | GET | Preview bronze table rows |
| `/api/silver/generate-sql` | POST | AI generate cleaning SQL from rules |
| `/api/silver/execute` | POST | Execute Silver transformation |
| `/api/gold/generate-kpi` | POST | AI discover KPIs from business requirement |
| `/api/gold/execute` | POST | Execute Gold KPI SQL and materialization |
| `/api/report/{project_id}` | GET | Generate full pipeline report |
| `/api/docs` | GET | Return platform documentation |

**Tech Stack:** FastAPI, Python 3.10+, SQLAlchemy ORM

---

### Data Access Layer (Repositories)

**Purpose:** Abstract database operations and source system connectivity

**Repositories:**

| Repository | Purpose |
|------------|---------|
| **Project Repository** | Metadata DB operations: projects, runs, execution logs |
| **Source Connectors** | PostgreSQL, CSV parsers, cloud storage adapters |
| **Bronze Repository** | Create/read Bronze schema tables, manage ingestion metadata |
| **Silver Repository** | Create/read Silver schema tables, store cleaning rules |
| **Gold Repository** | Create/read Gold schema tables, store KPI definitions |

---

### Database Layer

**Purpose:** Persistent storage for metadata, audit trails, and processed data

**Three-Database Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    AURUM Metadata DB                         │
│              (PostgreSQL - aurum_meta)                       │
├─────────────────────────────────────────────────────────────┤
│  • Projects (name, domain, env, created_at, updated_at)    │
│  • Runs (project_id, status, created_at, completed_at)     │
│  • Execution Logs (run_id, layer, status, message)         │
│  • SQL History (run_id, layer, rule, generated_sql)        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              User Source System                              │
│    (PostgreSQL / Snowflake / Databricks / S3 CSV)           │
├─────────────────────────────────────────────────────────────┤
│  • Original data in user's schema (e.g., public.orders)     │
│  • AURUM only reads; never modifies                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│         AURUM Processing Database                            │
│    (Same or separate PostgreSQL instance)                   │
├─────────────────────────────────────────────────────────────┤
│  • Bronze Schema → raw copies of ingested tables            │
│  • Silver Schema → cleaned, deduplicated tables             │
│  • Gold Schema → aggregated, business-ready KPI tables      │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow & Medallion Layers

### Bronze Layer (Raw Ingestion)

**Input:** Source tables from CSV or PostgreSQL  
**Process:**
1. Query source system or parse uploaded file
2. Detect schema and column types
3. Add metadata columns: `ingested_at`, `source_file`, `_bronze_hash`
4. Perform deduplication via hash (optional)
5. Write raw data to `bronze_database.bronze_<table_name>` schema

**Output:** Exact copy of source data with metadata enrichment

**Example:**
```sql
CREATE TABLE bronze.olist_orders_dataset AS
SELECT 
  *,
  NOW() AS ingested_at,
  'olist_orders_dataset' AS source_file,
  MD5(ROW(*)) AS _bronze_hash
FROM (SELECT * FROM source_db.public.olist_orders_dataset);
```

---

### Silver Layer (Cleaning & Transformation)

**Input:** User-defined cleaning rules (plain English)  
**Process:**
1. User enters rules: "Remove null customer_id", "Cast order_date to YYYY-MM-DD", etc.
2. Backend sends rules + Bronze schema to AI service
3. AI generates one `SELECT` statement per rule
4. User reviews and optionally edits SQL
5. Execute dry-run to preview cleaned data
6. Upon approval, execute full transformation

**Output:** Deduplicated, typed, cleaned tables in Silver schema

**Example Rule Flow:**
```
User Input:
  "Remove rows where customer_id is null"
  "Cast order_date to DATE format"
  "Trim whitespace from all text columns"

AI Generated SQL (per rule):
  SELECT * FROM bronze.olist_orders_dataset 
  WHERE customer_id IS NOT NULL;
  
  SELECT 
    CAST(order_date AS DATE) AS order_date,
    ... (other columns)
  FROM bronze.olist_orders_dataset;
  
  SELECT 
    TRIM(text_col) AS text_col,
    ... (numeric cols unchanged)
  FROM bronze.olist_orders_dataset;

Execution Result:
  bronze.olist_orders_dataset: 99,000 rows
  → silver.olist_orders_dataset: 97,500 rows (2,500 nulls removed)
```

---

### Gold Layer (KPI & Aggregation)

**Input:** Business requirement (e.g., "Executive sales dashboard with revenue trends, top customers, product performance")  
**Process:**
1. User enters business requirement in natural language
2. Backend queries Silver schema, identifies joinable tables
3. AI generates KPI discovery plan with aggregation SQL
4. Each KPI becomes one Gold table (denormalized, optimized for BI)
5. User approves KPI plan
6. System executes all KPI queries in parallel

**Output:** Multiple Gold tables, one per KPI, ready for BI/dashboard connection

**Example KPI Flow:**
```
User Requirement:
  "Executive sales dashboard: revenue by month, 
   top 10 customers by spend, product category performance"

AI Discovered KPIs:
  1. gold.olist_total_revenue_by_month
  2. gold.olist_top_10_customers_by_spend
  3. gold.olist_revenue_by_product_category

Generated SQL (example for #1):
  CREATE TABLE gold.olist_total_revenue_by_month AS
  SELECT 
    DATE_TRUNC('month', o.order_date)::DATE AS month,
    SUM(oi.price) AS total_revenue,
    COUNT(DISTINCT o.order_id) AS order_count
  FROM silver.olist_orders_dataset o
  JOIN silver.olist_order_items_dataset oi 
    ON o.order_id = oi.order_id
  WHERE o.order_status = 'delivered'
  GROUP BY DATE_TRUNC('month', o.order_date)
  ORDER BY month;
```

---

## Technology Stack

### Frontend
- **Framework:** React 18 with Hooks
- **Build Tool:** Vite
- **Styling:** TailwindCSS
- **HTTP Client:** Axios
- **State Management:** React Context API
- **Charts/Visualization:** (TBD - Chart.js or Recharts for report dashboard)

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **ORM:** SQLAlchemy
- **Database Drivers:** psycopg2 (PostgreSQL), other cloud connectors as needed
- **File Processing:** pandas (CSV parsing)
- **AI Integration:** OpenAI SDK, Ollama HTTP, Google Generative AI SDK

### Data Storage
- **Metadata DB:** PostgreSQL 13+
- **Processing DB:** PostgreSQL 13+ (can be same or separate instance)
- **File Storage:** Local filesystem (`./uploads/`) or cloud object storage (S3, GCS)

### Deployment
- **Backend:** Docker container, uvicorn ASGI server
- **Frontend:** Static build to CDN or web server
- **Orchestration:** Docker Compose (development), Kubernetes (production)

---

## API Architecture

### Request/Response Pattern

All API endpoints follow RESTful conventions:

**Success Response (200/201):**
```json
{
  "status": "success",
  "data": { ... },
  "message": "Operation completed"
}
```

**Error Response (4xx/5xx):**
```json
{
  "status": "error",
  "error_code": "INVALID_CONNECTION",
  "message": "PostgreSQL connection failed",
  "details": { ... }
}
```

### Async Job Handling

Long-running operations (bronze ingestion, silver execution, gold build) return a job ID immediately:

```json
{
  "job_id": "uuid-12345",
  "status": "queued",
  "estimated_duration_seconds": 45
}
```

Frontend polls `/api/jobs/{job_id}` for progress updates.

---

## Database Design

### Metadata Schema (aurum_meta)

```sql
-- Projects
CREATE TABLE projects (
  id UUID PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  domain VARCHAR(100),  -- Retail, Finance, Healthcare, etc.
  environment VARCHAR(20),  -- Dev, QA, Production
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Execution Runs
CREATE TABLE runs (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id),
  status VARCHAR(20),  -- queued, running, success, failed, warning
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  bronze_row_count INT,
  silver_row_count INT,
  gold_row_count INT,
  rows_removed INT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Execution Logs
CREATE TABLE execution_logs (
  id SERIAL PRIMARY KEY,
  run_id UUID REFERENCES runs(id),
  layer VARCHAR(20),  -- bronze, silver, gold
  table_name VARCHAR(255),
  status VARCHAR(20),  -- success, failed
  message TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- SQL History
CREATE TABLE sql_history (
  id SERIAL PRIMARY KEY,
  run_id UUID REFERENCES runs(id),
  layer VARCHAR(20),  -- silver, gold
  rule_or_kpi_name VARCHAR(255),
  generated_sql TEXT,
  user_edited_sql TEXT,  -- if user modified before execution
  executed_at TIMESTAMP,
  row_count_before INT,
  row_count_after INT
);
```

### Bronze/Silver/Gold Schemas (Processing DB)

Dynamically created per project run:

```
bronze.<table_name>_<run_id>
  - Exact copy of source
  - Added: ingested_at, source_file, _bronze_hash

silver.<table_name>_<run_id>
  - Cleaned, typed, deduplicated
  - Same columns as Bronze (transformed values)

gold.<kpi_name>_<run_id>
  - One row per KPI table
  - Aggregated, denormalized, BI-ready
```

---

## AI Integration Layer

### AI Service (`app/services/ai_service.py`)

**Supported Models:**

| Backend | Endpoint | Model | Use Case |
|---------|----------|-------|----------|
| **Google Gemini** | `generativelanguage.googleapis.com` | gemini-1.5-flash | Default (fast, cost-effective) |
| **Ollama** | `http://localhost:11434/api/generate` | codellama | Local, no API key required |
| **OpenAI** | `https://api.openai.com/v1/chat/completions` | gpt-4o | Premium, most capable |

**Prompts & Capabilities:**

1. **SQL Cleaning Rule Generator** (Silver Layer)
   - Input: Bronze schema + user rule (plain English)
   - Output: Valid PostgreSQL SELECT statement
   - Temperature: 0.1 (deterministic)
   - Max tokens: 2048

2. **KPI Discovery** (Gold Layer)
   - Input: Silver schema + business requirement
   - Output: List of KPI names + aggregation SQL
   - Temperature: 0.3 (creative but bounded)
   - Max tokens: 4096

3. **Error Recovery**
   - Input: Invalid SQL + error message
   - Output: Corrected SQL or explanation
   - Temperature: 0.2

**Response Parsing:**

- **Gemini:** `data["candidates"][0]["content"]["parts"][0]["text"]`
- **Ollama:** `data["response"]` (streaming, concatenate)
- **OpenAI:** `data["choices"][0]["message"]["content"]`

**Fallback Logic:**
```
Try Gemini (default)
  ↓ if rate-limited or timeout
Try Ollama (local fallback)
  ↓ if unavailable
Try OpenAI (premium fallback)
  ↓ if all fail
Return error with manual SQL editor option
```

---

## Security & Data Governance

### Authentication & Authorization
- (To be implemented) API key or OAuth2 for user identification
- Project-level access control (user can only access their projects)
- Read-only access to metadata DB; write access only to own project data

### Data Safety Principles

1. **Read-Only Source** — AURUM queries source systems; never modifies or deletes user data
2. **Append-Only Bronze** — Raw data is immutable after ingestion
3. **SELECT-Only Silver/Gold** — No destructive SQL (no DROP, DELETE, TRUNCATE)
4. **Explicit Approval** — All transformations require user sign-off before execution
5. **Audit Trail** — Every run logged with SQL, timestamps, row counts, user

### Data Minimization
- CSV uploads stored temporarily; deleted after Bronze ingestion
- Metadata DB contains only project names, schemas, and SQL history (no PII)
- User credentials (DB passwords) encrypted at rest and never logged

---

## Deployment & Scalability

### Development Environment

```bash
# Start all services via Docker Compose
docker-compose up

# Frontend: http://localhost:5173
# Backend: http://localhost:4000
# Metadata DB: PostgreSQL on localhost:5432
```

### Production Architecture

```
┌─────────────────────────────────────────┐
│      Reverse Proxy (nginx)              │
│   (TLS termination, load balancing)     │
└────────────┬────────────────────────────┘
             │
     ┌───────┴────────┐
     ▼                 ▼
┌─────────────┐  ┌─────────────┐
│   Backend   │  │   Frontend  │
│  Pod (x3)   │  │  CDN/Static │
│ (FastAPI)   │  │   Content   │
└────────┬────┘  └─────────────┘
         │
    ┌────┴─────┐
    ▼          ▼
┌──────────────────────────────────┐
│  Persistent Data Layer           │
│                                  │
│ • Metadata DB (PostgreSQL RDS)  │
│ • Processing DB (PostgreSQL RDS)│
│ • Object Storage (S3)            │
└──────────────────────────────────┘
```

### Scaling Considerations

1. **Horizontal Scaling:** Multiple FastAPI instances behind load balancer
2. **Job Queue:** Redis + Celery for long-running transformations (future)
3. **Database:** Connection pooling (SQLAlchemy pool_size, pool_recycle)
4. **Storage:** S3 for CSV uploads and pipeline reports (future)
5. **Caching:** Redis for schema metadata caching (future)

---

## Future Enhancements

- [ ] Multi-source joins (PostgreSQL + Snowflake in single pipeline)
- [ ] Scheduled runs and alerting
- [ ] Data lineage visualization
- [ ] Custom UDF support
- [ ] Web-based SQL editor with autocomplete
- [ ] Streaming ingestion (Kafka source connector)
- [ ] Advanced data profiling and anomaly detection
- [ ] Team collaboration and approval workflows

---

**Document Version:** 1.0  
**Last Updated:** July 2026  
**Status:** Active Development