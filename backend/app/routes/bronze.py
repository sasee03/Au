from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from typing import Optional
from app.models.schemas import BronzeIngestRequest
from app.services import bronze_service as svc
import json

router = APIRouter()


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    dataset_name: str = Form("dataset"),
    delimiter: str = Form("Comma (,)"),
    encoding: str = Form("utf-8"),
    first_row_header: bool = Form(True),
    project_id: Optional[str] = Form(None),
):
    contents = await file.read()
    result = await svc.ingest_csv(
        file_bytes=contents,
        dataset_name=dataset_name or file.filename.replace(".csv", ""),
        delimiter=delimiter,
        encoding=encoding,
        project_id=project_id or None,
    )
    return {"ok": True, **result}


@router.post("/ingest")
async def ingest_tables(body: BronzeIngestRequest):
    if body.source == "postgres" and body.pg_conn:
        conn_dict = body.pg_conn.model_dump(by_alias=False)
        result = await svc.ingest_postgres(
            pg_conn=conn_dict,
            tables=body.tables,
            project_id=body.project_id,
        )
    else:
        result = {"message": "CSV already ingested via /upload", "tables": body.tables}
    return {"ok": True, "result": result}


@router.get("/list")
async def list_bronze_tables():
    """Return all table names currently in the bronze schema."""
    return await svc.list_bronze_tables()


@router.get("/preview")
async def bronze_preview(
    table: str = Query(...),
    pg_conn: Optional[str] = Query(None),
):
    conn = None
    if pg_conn:
        try:
            conn = json.loads(pg_conn)
        except Exception:
            pass
    return await svc.get_bronze_preview(table_name=table, pg_conn=conn)
