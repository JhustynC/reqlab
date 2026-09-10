from __future__ import annotations

from fastapi import APIRouter, File, Response, UploadFile

from ..dependencies import get_repository, get_service, get_settings
from ..errors import bad_request, not_found
from ..schemas import TextSourceCreate


router = APIRouter(prefix="/projects/{project_id}", tags=["sources"])


@router.get("/sources")
def list_sources(project_id: str) -> list[dict]:
    try:
        get_repository().get_project(project_id)
        return get_repository().list_sources(project_id)
    except KeyError as error:
        raise not_found(error) from error


@router.post("/sources", status_code=201)
async def upload_sources(project_id: str, files: list[UploadFile] = File(...)) -> dict:
    if not files or len(files) > 20:
        raise bad_request(ValueError("Debe enviar entre 1 y 20 archivos por operación."))
    service = get_service()
    accepted: list[dict] = []
    errors: list[dict] = []
    for upload in files:
        content = await upload.read()
        if len(content) > get_settings().max_upload_bytes:
            errors.append({"filename": upload.filename, "detail": "El archivo excede el límite permitido."})
            continue
        try:
            accepted.append(
                service.ingest(
                    project_id,
                    upload.filename or "fuente.txt",
                    content,
                    upload.content_type or "",
                    index_after=False,
                )
            )
        except (ValueError, RuntimeError, KeyError) as error:
            errors.append({"filename": upload.filename, "detail": str(error)})
    if accepted:
        try:
            service.reindex(project_id)
            get_repository().mark_project_sources_indexed(project_id)
        except Exception as error:
            errors.append({"filename": "índice vectorial", "detail": str(error)})
    return {"accepted": accepted, "errors": errors, "fragment_count": get_repository().count_fragments(project_id)}


@router.post("/sources/text", status_code=201)
def create_text_source(project_id: str, payload: TextSourceCreate) -> dict:
    """Registra texto libre pegado por el usuario como una fuente trazable."""
    try:
        return get_service().ingest_text(
            project_id,
            payload.title,
            payload.text,
            payload.source_type,
        )
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


@router.get("/sources/{source_id}/preview")
def preview_source(project_id: str, source_id: str) -> dict:
    try:
        return get_service().preview_source(project_id, source_id)
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise bad_request(error) from error


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(project_id: str, source_id: str) -> Response:
    try:
        get_service().delete_source(project_id, source_id)
        return Response(status_code=204)
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


@router.get("/fragments")
def list_fragments(project_id: str, source_code: str | None = None) -> list[dict]:
    try:
        get_repository().get_project(project_id)
        return get_repository().list_fragment_summaries(project_id, source_code)
    except KeyError as error:
        raise not_found(error) from error


@router.get("/fragments/{fragment_key}")
def get_fragment(project_id: str, fragment_key: str) -> dict:
    try:
        return get_repository().get_fragment(project_id, fragment_key)
    except KeyError as error:
        raise not_found(error) from error
