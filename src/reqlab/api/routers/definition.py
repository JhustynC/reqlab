from __future__ import annotations

from fastapi import APIRouter

from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import DefinitionAnswersUpdate


router = APIRouter(prefix="/projects/{project_id}/definition", tags=["definition"])


@router.get("/questions")
def questions(project_id: str) -> list[dict]:
    try:
        get_repository().get_project(project_id)
        return get_repository().list_questions(project_id)
    except KeyError as error:
        raise not_found(error) from error


@router.post("/analyze")
def analyze(project_id: str) -> dict:
    try:
        analysis = get_service().analyze_definition(project_id)
        return {"analysis": analysis, "questions": get_repository().list_questions(project_id)}
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


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
def confirm(project_id: str) -> dict:
    try:
        return {"profile": get_service().confirm_definition(project_id)}
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
