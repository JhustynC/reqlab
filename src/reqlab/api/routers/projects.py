from __future__ import annotations

from fastapi import APIRouter, Response

from ...services import ProjectApplicationService
from ...storage import SQLiteRepository
from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import ProjectArchiveUpdate, ProjectCreate


router = APIRouter(prefix="/projects", tags=["projects"])


def summary(repository: SQLiteRepository, project: dict) -> dict:
    return project | {
        "source_count": len(repository.list_sources(project["id"])),
        "fragment_count": repository.count_fragments(project["id"]),
        "artifact_count": len(repository.list_artifacts(project["id"])),
    }


@router.get("")
def list_projects(archived: bool = False) -> list[dict]:
    repository = get_repository()
    return [summary(repository, item) for item in repository.list_projects(archived=archived)]


@router.post("", status_code=201)
def create_project(payload: ProjectCreate) -> dict:
    service: ProjectApplicationService = get_service()
    try:
        return summary(get_repository(), service.create_project(payload.name, payload.description, payload.domain))
    except ValueError as error:
        raise bad_request(error) from error


@router.get("/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        return summary(get_repository(), get_repository().get_project(project_id))
    except KeyError as error:
        raise not_found(error) from error


@router.patch("/{project_id}/archive")
def set_project_archived(project_id: str, payload: ProjectArchiveUpdate) -> dict:
    try:
        project = get_service().archive_project(project_id, payload.archived)
        return summary(get_repository(), project)
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str) -> Response:
    try:
        get_service().delete_project(project_id)
        return Response(status_code=204)
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error
