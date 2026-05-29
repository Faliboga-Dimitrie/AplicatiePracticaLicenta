from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ...access_control import UserRecord
from ..dependencies import get_artifact_service, get_current_user
from ..errors import unwrap_result
from ..schemas import CaseArtifactsResponse
from ..serialization import case_artifacts_to_dict
from ..services import ArtifactService

router = APIRouter()


@router.get("/{case_id}/artifacts", response_model=CaseArtifactsResponse)
def list_case_artifacts(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    artifacts: ArtifactService = Depends(get_artifact_service),
):
    """
    List frontend-safe artifact references for one authorized MRI case.

    React should call this after preprocessing/mesh jobs complete. The response
    contains URLs for meshes, wireframes, metrics, QC images and useful NIfTI
    outputs, but it does not expose local filesystem paths.
    """
    result = artifacts.list_for_case(current_user, case_id)
    bundle = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to view artifacts.",
    )
    return case_artifacts_to_dict(bundle)


@router.get("/{case_id}/viewer-artifacts", response_model=CaseArtifactsResponse)
def list_case_viewer_artifacts(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    artifacts: ArtifactService = Depends(get_artifact_service),
):
    """List only artifacts needed by the interactive 3D viewer.

    This endpoint intentionally omits QC images and NIfTI preprocessing outputs.
    It returns GLB meshes, GLB wireframes and metrics JSON metadata references,
    so the viewer page does not preflight/download large irrelevant files.
    """
    result = artifacts.list_viewer_for_case(current_user, case_id)
    bundle = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to view 3D artifacts.",
    )
    return case_artifacts_to_dict(bundle)


@router.get("/{case_id}/artifacts/{artifact_name:path}")
def get_case_artifact(
    case_id: int,
    artifact_name: str,
    current_user: UserRecord = Depends(get_current_user),
    artifacts: ArtifactService = Depends(get_artifact_service),
):
    """
    Serve one known artifact file for an authorized MRI case.

    The path parameter is not used as a filesystem path. ArtifactService only
    returns files that are part of the case's known artifact manifest, which
    avoids path traversal and prevents exposing arbitrary local files.
    """
    result = artifacts.get_file_for_case(current_user, case_id, artifact_name)
    artifact = unwrap_result(
        result,
        not_found_message="Artifact not found for this MRI case.",
    )

    if not artifact.path.exists() or not artifact.path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file no longer exists.")

    return FileResponse(
        path=artifact.path,
        media_type=artifact.ref.mime_type,
        filename=artifact.path.name,
    )
