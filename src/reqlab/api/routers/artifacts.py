from __future__ import annotations

from fastapi import APIRouter, Query

from ..dependencies import get_repository, get_service
from ..errors import bad_request, not_found
from ..schemas import ArtifactUpdate, RevisionDecision, RevisionRequest


router = APIRouter(prefix="/projects/{project_id}", tags=["artifacts"])


@router.get("/artifacts")
def list_artifacts(project_id: str, artifact_type: str | None = Query(default=None, pattern="^(RF|RNF|HU)$")) -> list[dict]:
    try:
        get_repository().get_project(project_id)
        return get_repository().list_artifacts(project_id, artifact_type)
    except KeyError as error:
        raise not_found(error) from error


@router.put("/artifacts/{artifact_id}")
def update_artifact(project_id: str, artifact_id: str, payload: ArtifactUpdate) -> dict:
    try:
        artifact = get_repository().get_artifact(artifact_id)
        if artifact["project_id"] != project_id:
            raise KeyError("El artefacto no pertenece al proyecto indicado.")
        return get_service().save_manual_revision(artifact_id, payload.model_dump())
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.get("/artifacts/{artifact_id}/versions")
def versions(project_id: str, artifact_id: str) -> list[dict]:
    try:
        artifact = get_repository().get_artifact(artifact_id)
        if artifact["project_id"] != project_id:
            raise KeyError("El artefacto no pertenece al proyecto indicado.")
        return get_repository().list_versions(artifact_id)
    except KeyError as error:
        raise not_found(error) from error


@router.post("/artifacts/{artifact_id}/revision-proposals", status_code=201)
def propose_revision(project_id: str, artifact_id: str, payload: RevisionRequest) -> dict:
    try:
        artifact = get_repository().get_artifact(artifact_id)
        if artifact["project_id"] != project_id:
            raise KeyError("El artefacto no pertenece al proyecto indicado.")
        return get_service().create_revision_proposal(project_id, artifact_id, payload.instruction)
    except KeyError as error:
        raise not_found(error) from error
    except (ValueError, RuntimeError) as error:
        raise bad_request(error) from error


@router.post("/revision-proposals/{proposal_id}/decision")
def decide_revision(project_id: str, proposal_id: str, payload: RevisionDecision) -> dict:
    try:
        proposal = get_repository().get_revision_proposal(proposal_id)
        if proposal["project_id"] != project_id:
            raise KeyError("La propuesta no pertenece al proyecto indicado.")
        return get_service().decide_revision_proposal(proposal_id, payload.accept)
    except KeyError as error:
        raise not_found(error) from error
    except ValueError as error:
        raise bad_request(error) from error


@router.get("/validation")
def latest_validation(project_id: str) -> dict:
    try:
        get_repository().get_project(project_id)
        return get_repository().latest_validation_report(project_id) or {"report": None, "created_at": None}
    except KeyError as error:
        raise not_found(error) from error

