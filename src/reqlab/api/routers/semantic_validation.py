from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from ..dependencies import get_repository, get_service, get_settings
from ..errors import bad_request, not_found


router = APIRouter(prefix="/projects/{project_id}/semantic-validation", tags=["semantic-validation"])


def execute_semantic_validation(project_id: str, run_id: str) -> None:
    try:
        get_service().run_semantic_validation(project_id, run_id=run_id)
    except Exception:
        # El servicio cierra la ejecución con el error. La tarea no debe afectar
        # generación, edición ni consulta de los artefactos existentes.
        return


@router.post("", status_code=202)
def start_semantic_validation(project_id: str, background_tasks: BackgroundTasks) -> dict:
    try:
        repository = get_repository()
        repository.get_project(project_id)
        artifacts = repository.list_artifacts(project_id)
        if not artifacts:
            raise ValueError("El proyecto todavía no tiene artefactos para validar.")
        settings = get_settings()
        if not settings.semantic_validation_enabled:
            raise ValueError(
                "La validación semántica está desactivada. Configure SEMANTIC_VALIDATION_ENABLED=True."
            )
        if not settings.typesafe_api_key:
            raise ValueError(
                "La validación semántica está activada, pero TYPESAFE_API_KEY no está configurada."
            )
        run_id = repository.start_run(
            project_id,
            "semantic_validation",
            "semantic.validator",
            {
                "mode": settings.semantic_validation_mode,
                "model": settings.typesafe_model,
                "prompt_version": settings.semantic_prompt_version,
                "confidence_threshold": settings.semantic_confidence_threshold,
                "progress": 0,
                "step": "queued",
                "message": "Validación semántica en cola",
            },
        )
        background_tasks.add_task(execute_semantic_validation, project_id, run_id)
        return {"run_id": run_id, "status": "running"}
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.get("")
def semantic_validation_status(project_id: str) -> dict:
    try:
        return get_service().semantic_validation_status(project_id)
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error
