from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import ProjectCreate, ProjectOut
from app.repositories import project_repository as repo

router = APIRouter()


@router.post("", response_model=dict, status_code=201)
async def create_project(data: ProjectCreate):
    row = await repo.create(data)
    if not row:
        raise HTTPException(500, "Failed to create project")
    return row


@router.get("", response_model=list)
async def list_projects(limit: int = Query(50, ge=1, le=200)):
    return await repo.list_all(limit=limit)


@router.get("/{project_id}", response_model=dict)
async def get_project(project_id: str):
    row = await repo.get_by_id(project_id)
    if not row:
        raise HTTPException(404, "Project not found")
    return row


@router.get("/{project_id}/runs", response_model=list)
async def get_runs(project_id: str):
    return await repo.get_runs(project_id)
