from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


def workspace_to_dict(workspace: Any | None) -> dict[str, object] | None:
    """Return frontend-safe workspace state without local filesystem paths."""
    if workspace is None:
        return None

    raw_exists = workspace.raw_path.exists()
    reoriented_exists = workspace.reoriented_path.exists()
    skull_stripped_exists = workspace.skull_stripped_path.exists()
    skull_mask_exists = workspace.skull_stripped_mask_path.exists()
    fast_seg_exists = workspace.fast_seg_path.exists()
    fast_pve_outputs_exist = bool(getattr(workspace, "has_fast_pve_outputs", False))
    fast_outputs_exist = bool(getattr(workspace, "has_fast_outputs", False))
    metrics_exists = workspace.metrics_json_path.exists()
    any_mesh_outputs_exist = bool(getattr(workspace, "has_any_mesh_outputs", False))
    complete_mesh_outputs_exist = bool(getattr(workspace, "has_complete_mesh_outputs", False))

    return {
        "case_id": getattr(workspace, "case_id", None),
        "subject_id": getattr(workspace, "subject_id", None),
        "acquisition_date": getattr(workspace, "acquisition_date", None),
        "exists": bool(getattr(workspace, "workspace_exists", False)),
        "raw_exists": raw_exists,
        "directories": {
            "input_mri": workspace.input_mri_dir.exists(),
            "reoriented": workspace.reoriented_dir.exists(),
            "hd_bet": workspace.hd_bet_dir.exists(),
            "fast": workspace.fast_dir.exists(),
            "mesh": workspace.mesh_dir.exists(),
        },
        "outputs": {
            "reoriented": reoriented_exists,
            "skull_stripped": skull_stripped_exists,
            "skull_stripped_mask": skull_mask_exists,
            "fast_segmentation": fast_seg_exists,
            "fast_pve_outputs": fast_pve_outputs_exist,
            "fast_outputs": fast_outputs_exist,
            "metrics_json": metrics_exists,
            "any_mesh_outputs": any_mesh_outputs_exist,
            "complete_mesh_outputs": complete_mesh_outputs_exist,
        },
    }


def case_capabilities_to_dict(case: Any) -> dict[str, bool]:
    workspace = getattr(case, "workspace", None)
    status = (getattr(case, "status", None) or "").lower()

    active_statuses = {
        "preprocessing_queued",
        "preprocessing",
        "mesh_queued",
        "mesh_analysis",
    }
    is_busy = status in active_statuses

    if workspace is None:
        return {
            "raw_uploaded": False,
            "can_start_preprocessing": False,
            "can_start_mesh_analysis": False,
            "can_view_artifacts": False,
            "can_view_meshes": False,
            "can_view_metrics": False,
            "is_busy": is_busy,
        }

    raw_exists = workspace.raw_path.exists()
    has_fast_pve_outputs = bool(getattr(workspace, "has_fast_pve_outputs", False))
    has_any_mesh_outputs = bool(getattr(workspace, "has_any_mesh_outputs", False))
    has_metrics = workspace.metrics_json_path.exists()
    can_view_artifacts = any([
        raw_exists,
        workspace.reoriented_path.exists(),
        workspace.skull_stripped_path.exists(),
        has_fast_pve_outputs,
        has_any_mesh_outputs,
        has_metrics,
    ])

    return {
        "raw_uploaded": raw_exists,
        "has_reoriented": workspace.reoriented_path.exists(),
        "has_skull_stripped": workspace.skull_stripped_path.exists(),
        "has_fast_outputs": bool(getattr(workspace, "has_fast_outputs", False)),
        "has_fast_pve_outputs": has_fast_pve_outputs,
        "has_meshes": has_any_mesh_outputs,
        "has_metrics": has_metrics,
        "can_start_preprocessing": raw_exists and not is_busy,
        "can_start_mesh_analysis": has_fast_pve_outputs and not is_busy,
        "can_view_artifacts": can_view_artifacts,
        "can_view_meshes": has_any_mesh_outputs,
        "can_view_metrics": has_metrics,
        "is_busy": is_busy,
    }


def user_to_dict(user: Any) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
    }


def subject_to_dict(subject: Any) -> dict[str, object]:
    return {
        "id": subject.id,
        "name": subject.name,
        "age": subject.age,
        "notes": subject.notes,
    }


def mri_case_to_dict(case: Any) -> dict[str, object]:
    acquisition_date = case.acquisition_date
    if hasattr(acquisition_date, "isoformat"):
        acquisition_date = acquisition_date.isoformat()

    return {
        "id": case.id,
        "subject_id": case.subject_id,
        "acquisition_date": acquisition_date,
        "notes": case.notes,
        "status": case.status,
        "case_key": getattr(case, "case_key", None),
        "workspace": workspace_to_dict(getattr(case, "workspace", None)),
        "capabilities": case_capabilities_to_dict(case),
    }


def subject_summary_to_dict(subject_summary: Any) -> dict[str, object]:
    subject = subject_summary.subject

    return {
        "id": subject.id,
        "name": subject.name,
        "age": subject.age,
        "notes": subject.notes,
        "role": subject_summary.role,
        "case_count": int(subject_summary.case_count or 0),
    }

def subject_with_cases_to_dict(
    subject_with_cases: Any,
    *,
    include_cases: bool = True,
) -> dict[str, object]:
    subject = subject_with_cases.subject
    cases = list(subject_with_cases.cases or [])

    result: dict[str, object] = {
        "id": subject.id,
        "name": subject.name,
        "age": subject.age,
        "notes": subject.notes,
        "role": subject_with_cases.role,
        "case_count": len(cases),
    }

    if include_cases:
        result["cases"] = [mri_case_to_dict(case) for case in cases]

    return result



def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def job_to_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "user_id": job.user_id,
        "case_id": job.case_id,
        "message": job.message,
        "progress": job.progress,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "result": _json_safe(job.result),
        "error": job.error,
        "metadata": _json_safe(job.metadata) or {},
        "cancel_requested": job.cancel_requested,
    }



def artifact_to_dict(artifact) -> dict[str, Any]:
    ref = artifact.ref
    return {
        "name": ref.name,
        "kind": ref.kind.value,
        "url": ref.uri,
        "mime_type": ref.mime_type,
        "size_bytes": artifact.size_bytes,
        "metadata": _json_safe(dict(ref.metadata or {})) or {},
    }


def case_artifacts_to_dict(bundle) -> dict[str, Any]:
    return {
        "case_id": bundle.case_db_id,
        "case_key": bundle.case_key,
        "subject_id": bundle.subject_id,
        "acquisition_date": bundle.acquisition_date,
        "artifacts": [artifact_to_dict(artifact) for artifact in bundle.artifacts],
    }
