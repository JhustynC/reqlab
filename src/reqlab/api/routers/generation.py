from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from ...generation_budget import validate_generation_limits
from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import GenerationRequest, GenerationResumeRequest


router = APIRouter(tags=["generation"])


def execute_generation(
    project_id: str,
    limits_by_type: dict[str, int],
    run_id: str,
    resume_from_run_id: str | None = None,
) -> None:
    repository = get_repository()

    def progress(percent: int, message: str, step: str) -> None:
        repository.update_run_progress(run_id, percent, message, step)

    try:
        get_service().generate_artifacts(
            project_id,
            limits_by_type=limits_by_type,
            run_id=run_id,
            progress_callback=progress,
            resume_from_run_id=resume_from_run_id,
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
        latest = repository.latest_run(project_id)
        if latest and latest["status"] == "running":
            return {
                "run_id": latest["id"],
                "status": "running",
                "limits": latest["parameters"].get("generation_limits", payload.resolved_limits()),
                "resumed": True,
            }
        if repository.list_artifacts(project_id) and latest and latest["status"] == "failed":
            raise ValueError(
                "Existe una generación parcial recuperable. Reanude la ejecución fallida "
                "para conservar los agentes ya completados."
            )
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


@router.post("/projects/{project_id}/generation/resume", status_code=202)
def resume_generation(
    project_id: str,
    payload: GenerationResumeRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    repository = get_repository()
    try:
        project = repository.get_project(project_id)
        if not project["definition_confirmed"]:
            raise ValueError("La definición del proyecto debe estar confirmada.")
        previous = repository.get_run(payload.run_id)
        current = repository.latest_run(project_id)
        if current and current["status"] == "running":
            return {
                "run_id": current["id"],
                "status": "running",
                "limits": current["parameters"].get("generation_limits", {}),
                "resumed_from_run_id": current["parameters"].get("resumed_from_run_id"),
            }
        if previous["project_id"] != project_id:
            raise ValueError("La ejecución no pertenece a este proyecto.")
        if previous["agent_id"] != "orchestrator.main" or previous["phase"] != "generation":
            raise ValueError("Solo se puede reanudar una generación principal.")
        if previous["status"] != "failed":
            raise ValueError("Solo se puede reanudar una ejecución fallida.")
        limits = previous["parameters"].get("generation_limits")
        if not isinstance(limits, dict):
            raise ValueError("La ejecución no conserva sus límites de generación.")
        limits_by_type = {key: int(limits[key]) for key in ("RF", "RNF", "HU")}
        parameters = {
            key: value
            for key, value in previous["parameters"].items()
            if key not in {"metrics", "progress", "step", "message"}
        }
        parameters.update(
            {
                "progress": 0,
                "step": "queued",
                "message": "Reanudación en cola",
                "resumed_from_run_id": previous["id"],
            }
        )
        run_id = repository.start_run(
            project_id, "generation", "orchestrator.main", parameters
        )
        background_tasks.add_task(
            execute_generation,
            project_id,
            limits_by_type,
            run_id,
            previous["id"],
        )
        return {
            "run_id": run_id,
            "status": "running",
            "limits": limits_by_type,
            "resumed_from_run_id": previous["id"],
        }
    except KeyError as error:
        raise not_found(error) from error
    except (TypeError, ValueError) as error:
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
