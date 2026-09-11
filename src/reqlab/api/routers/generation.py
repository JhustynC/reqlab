from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from ...generation_budget import validate_generation_limits
from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import GenerationRequest


router = APIRouter(tags=["generation"])


def execute_generation(project_id: str, limits_by_type: dict[str, int], run_id: str) -> None:
    repository = get_repository()

    def progress(percent: int, message: str, step: str) -> None:
        repository.update_run_progress(run_id, percent, message, step)

    try:
        get_service().generate_artifacts(
            project_id,
            limits_by_type=limits_by_type,
            run_id=run_id,
            progress_callback=progress,
        )
    except Exception as error:
        # El servicio registra los fallos del flujo normal. Este cierre adicional
        # cubre también errores que ocurran antes de que el orquestador arranque.
        repository.finish_run(run_id, "failed", str(error))
        repository.update_project_status(project_id, "ready_to_generate")


@router.get("/projects/{project_id}/generation/recommendations")
def generation_recommendations(project_id: str) -> dict:
    try:
        return get_service().generation_recommendations(project_id)
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.post("/projects/{project_id}/generation", status_code=202)
def generate(project_id: str, payload: GenerationRequest, background_tasks: BackgroundTasks) -> dict:
    repository = get_repository()
    try:
        project = repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La definición del proyecto debe estar confirmada.")
        service = get_service()
        limits_by_type = payload.resolved_limits()
        recommendations = service.generation_recommendations(project_id)
        if payload.limits is not None:
            limits_by_type = validate_generation_limits(limits_by_type, recommendations)
        run_parameters = service.run_parameters(limits_by_type, recommendations)
        run_parameters.update({
            "progress": 0,
            "step": "queued",
            "message": "Ejecución en cola",
        })
        run_id = repository.start_run(
            project_id,
            "generation",
            "orchestrator.main",
            run_parameters,
        )
        background_tasks.add_task(execute_generation, project_id, limits_by_type, run_id)
        return {"run_id": run_id, "status": "running", "limits": limits_by_type}
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return get_repository().get_run(run_id)
    except KeyError as error:
        raise not_found(error) from error


@router.get("/projects/{project_id}/runs/latest")
def latest_project_run(project_id: str) -> dict:
    try:
        get_repository().get_project(project_id)
        return {"run": get_repository().latest_run(project_id)}
    except KeyError as error:
        raise not_found(error) from error
