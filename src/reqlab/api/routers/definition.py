from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import DefinitionAnswersUpdate, DefinitionConfirmRequest


router = APIRouter(prefix="/projects/{project_id}/definition", tags=["definition"])


def execute_definition(project_id: str, run_id: str) -> None:
    repository = get_repository()

    def progress(percent: int, message: str, step: str) -> None:
        repository.update_run_progress(run_id, percent, message, step)

    try:
        analysis = get_service().analyze_definition(
            project_id,
            progress_callback=progress,
        )
        progress(100, "Interpretación provisional disponible", "completed")
        metrics = {
            "coverage": analysis.get("coverage", {}),
            "llm": get_service().client.get_last_telemetry(),
        }
        repository.finish_run(run_id, "completed", metrics=metrics)
    except Exception as error:
        repository.finish_run(
            run_id,
            "failed",
            str(error),
            metrics={"llm": get_service().client.get_last_telemetry()},
        )


@router.get("/questions")
def questions(project_id: str) -> list[dict]:
    try:
        get_repository().get_project(project_id)
        return get_repository().list_questions(project_id)
    except KeyError as error:
        raise not_found(error) from error


@router.post("/analyze", status_code=202)
def analyze(project_id: str, background_tasks: BackgroundTasks) -> dict:
    try:
        repository = get_repository()
        repository.get_project(project_id)
        if repository.count_fragments(project_id) < 1:
            raise ValueError("Primero debe cargar y procesar al menos una fuente.")
        current = repository.latest_run(project_id, agent_id="definition.main")
        if current and current["status"] == "running":
            return {"run_id": current["id"], "status": "running", "resumed": True}
        run_id = repository.start_run(
            project_id,
            "definition",
            "definition.main",
            {
                "progress": 0,
                "step": "queued",
                "message": "Análisis de definición en cola",
                "experimental_config": (
                    get_service().settings.experimental_snapshot()
                    if get_service().settings
                    else {}
                ),
            },
        )
        background_tasks.add_task(execute_definition, project_id, run_id)
        return {"run_id": run_id, "status": "running", "resumed": False}
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


@router.get("/run/latest")
def latest_definition_run(project_id: str) -> dict:
    try:
        repository = get_repository()
        repository.get_project(project_id)
        return {"run": repository.latest_run(project_id, agent_id="definition.main")}
    except KeyError as error:
        raise not_found(error) from error


@router.put("/answers")
def save_answers(project_id: str, payload: DefinitionAnswersUpdate) -> dict:
    try:
        get_repository().get_project(project_id)
        known = {item["question_key"] for item in get_repository().list_questions(project_id)}
        unknown = [item.question_key for item in payload.answers if item.question_key not in known]
        if unknown:
            raise ValueError(f"Preguntas desconocidas: {', '.join(unknown)}")
        for item in payload.answers:
            get_repository().save_answer(project_id, item.question_key, item.answer)
        return {"questions": get_repository().list_questions(project_id)}
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.post("/confirm")
def confirm(project_id: str, payload: DefinitionConfirmRequest) -> dict:
    try:
        return {
            "profile": get_service().confirm_definition(
                project_id, reset_generation=payload.reset_generation
            ),
            "generation_reset": payload.reset_generation,
        }
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


@router.get("")
def profile(project_id: str) -> dict:
    try:
        get_repository().get_project(project_id)
        return get_repository().get_profile(project_id) or {"profile": None, "confirmed_at": None}
    except KeyError as error:
        raise not_found(error) from error
