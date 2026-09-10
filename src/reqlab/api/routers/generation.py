from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import GenerationRequest


router = APIRouter(tags=["generation"])


def execute_generation(project_id: str, limit_per_type: int, run_id: str) -> None:
    repository = get_repository()

    def progress(percent: int, message: str, step: str) -> None:
        repository.update_run_progress(run_id, percent, message, step)

    try:
        get_service().generate_artifacts(
            project_id,
            limit_per_type=limit_per_type,
            run_id=run_id,
            progress_callback=progress,
        )
    except Exception as error:
        # El servicio registra los fallos del flujo normal. Este cierre adicional
        # cubre también errores que ocurran antes de que el orquestador arranque.
        repository.finish_run(run_id, "failed", str(error))
        repository.update_project_status(project_id, "ready_to_generate")


@router.post("/projects/{project_id}/generation", status_code=202)
def generate(project_id: str, payload: GenerationRequest, background_tasks: BackgroundTasks) -> dict:
    repository = get_repository()
    try:
        project = repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La definición del proyecto debe estar confirmada.")
        run_id = repository.start_run(
            project_id,
            "generation",
            "orchestrator.main",
            {
                "model": get_service().client.model,
                "limit_per_type": payload.limit_per_type,
                "retrieval": "hybrid_rrf",
                "progress": 0,
                "step": "queued",
                "message": "Ejecución en cola",
            },
        )
        background_tasks.add_task(execute_generation, project_id, payload.limit_per_type, run_id)
        return {"run_id": run_id, "status": "running"}
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
