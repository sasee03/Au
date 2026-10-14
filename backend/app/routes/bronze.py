from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from typing import Optional
from app.models.schemas import (
    BronzeDictionaryRequest,
    BronzeIngestRequest,
    DQJobRequest,
    DQReportRequest,
    PgConnConfig,
)
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
    connection: Optional[str] = Form(None),
):
    contents = await file.read()
    dictionary_connection = None
    if connection:
        try:
            parsed_connection = json.loads(connection)
            if not isinstance(parsed_connection, dict):
                raise ValueError("Connection must be a JSON object")
            dictionary_connection = PgConnConfig.model_validate(
                parsed_connection
            ).model_dump(by_alias=False)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid connection: {exc}") from exc
    try:
        result = await svc.ingest_csv(
            file_bytes=contents,
            dataset_name=dataset_name or file.filename.replace(".csv", ""),
            delimiter=delimiter,
            encoding=encoding,
            project_id=project_id or None,
            dictionary_connection=dictionary_connection,
            source_filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
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


@router.post("/dictionary")
async def data_dictionary(
    body: BronzeDictionaryRequest,
):
    return await svc.get_data_dictionary(
        body.pg_conn.model_dump(by_alias=False), table=body.table
    )


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


@router.post("/quality-report")
async def quality_report(body: DQReportRequest):
    try:
        await svc.validate_sync_dq_size(body.tables)
        return await svc.run_dq_check(
            body.project_id,
            body.tables,
            pg_conn=body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None,
        )
    except svc.DQReportTooLargeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/quality-report/jobs", status_code=202)
async def create_quality_report_job(body: DQJobRequest):
    try:
        job_id = await svc.create_dq_job(
            body.project_id,
            body.tables,
            body.pg_conn.model_dump(by_alias=False) if body.pg_conn else None,
        )
        return {"job_id": job_id}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/quality-report/jobs/{job_id}")
async def get_quality_report_job(job_id: str):
    try:
        result = await svc.get_dq_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.post("/quality-report/jobs/{job_id}/cancel")
async def cancel_quality_report_job(job_id: str):
    try:
        return await svc.cancel_dq_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/quality-report/impacted-rows")
async def impacted_rows(payload: dict):
    return await svc.get_impacted_rows(
        table=payload.get("table"),
        column=payload.get("column"),
        check=payload.get("check"),
        page=int(payload.get("page", 1)),
        page_size=int(payload.get("page_size", 50)),
        parent_table=payload.get("parent_table"),
        pk_column=payload.get("pk_column"),
    )
