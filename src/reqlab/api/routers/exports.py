from __future__ import annotations

import re

from fastapi import APIRouter, Response

from ...exporters import build_docx
from ...services import project_export_json, project_export_payload
from ..dependencies import get_repository
from ..errors import not_found


router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])


def filename(project_name: str, suffix: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", project_name).strip("_") or "proyecto"
    return f"{safe}_requisitos.{suffix}"


@router.get("/json")
def export_json(project_id: str) -> Response:
    try:
        repository = get_repository()
        project = repository.get_project(project_id)
        content = project_export_json(repository, project_id)
        repository.update_project_status(project_id, "exported")
        return Response(
            content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename(project["name"], "json")}"'},
        )
    except KeyError as error:
        raise not_found(error) from error


@router.get("/docx")
def export_docx(project_id: str) -> Response:
    try:
        repository = get_repository()
        project = repository.get_project(project_id)
        content = build_docx(project_export_payload(repository, project_id))
        repository.update_project_status(project_id, "exported")
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename(project["name"], "docx")}"'},
        )
    except KeyError as error:
        raise not_found(error) from error
