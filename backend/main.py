import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.config import settings
from app.database import init_db, close_db
from app.routes import projects, postgres, bronze, silver, gold, report, docs

app = FastAPI(
    title="AURUM API",
    description="Enterprise Data Quality Operating System — Backend",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# IMPORTANT: CORSMiddleware must be added first, before any router.
# allow_credentials=True requires explicit origins (not "*").
# allow_headers must list every header the browser sends in the preflight.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # open for local dev; lock down in production
    allow_credentials=False,      # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)

# ── Startup / Shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    await init_db()

@app.on_event("shutdown")
async def shutdown():
    await close_db()

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(projects.router,  prefix="/api/projects",  tags=["Projects"])
app.include_router(postgres.router,  prefix="/api/postgres",  tags=["PostgreSQL"])
app.include_router(bronze.router,    prefix="/api/bronze",    tags=["Bronze"])
app.include_router(silver.router,    prefix="/api/silver",    tags=["Silver"])
app.include_router(gold.router,      prefix="/api/gold",      tags=["Gold"])
app.include_router(report.router,    prefix="/api/report",    tags=["Report"])
app.include_router(docs.router,      prefix="/api/docs",      tags=["Docs"])

@app.get("/api/health", tags=["Health"])
async def health():
    from datetime import datetime
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
