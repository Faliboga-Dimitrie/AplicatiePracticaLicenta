from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_access_service, get_settings
from ...access_control import AccessControlService
from ...project_core import MRICase
from ...mri_preprocessing.pipeline import build_default_preprocessing_pipeline

router = APIRouter()


@router.post("/{case_id}/preprocess")
def preprocess_case(
    case_id: int,
    access: AccessControlService = Depends(get_access_service),
    settings=Depends(get_settings),
):
    case_result = access.get_mri_case(case_id, include_workspace=True)

    if not case_result.success:
        raise HTTPException(status_code=500, detail=case_result.error)

    case_record = case_result.data
    if case_record is None:
        raise HTTPException(status_code=404, detail="MRI case not found.")

    workspace = case_record.workspace
    if workspace is None:
        raise HTTPException(status_code=500, detail="Workspace could not be resolved.")

    case = MRICase(
        subject_id=case_record.subject_id,
        acquisition_date=case_record.acquisition_date.isoformat(),
        raw_path=workspace.raw_path,
    )

    pipeline = build_default_preprocessing_pipeline(settings)

    try:
        result = pipeline.run_case(case)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "subject_id": result.subject_id,
        "acquisition_date": result.workspace.acquisition_date,
        "reoriented_path": str(result.reoriented_path),
        "skull_stripped_path": str(result.skull_stripped_path),
        "segmentation_path": str(result.segmentation_path),
        "pve_paths": {k: str(v) for k, v in result.pve_paths.items()},
    }