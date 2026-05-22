from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any


def workspace_to_dict(workspace: Any | None) -> dict[str, object] | None:
    if workspace is None:
        return None

    return {
        "case_id": getattr(workspace, "case_id", None),
        "subject_id": getattr(workspace, "subject_id", None),
        "acquisition_date": getattr(workspace, "acquisition_date", None),

        "raw_path": str(workspace.raw_path),
        "raw_exists": workspace.raw_path.exists(),

        "directories": {
            "input_mri_dir": {
                "path": str(workspace.input_mri_dir),
                "exists": workspace.input_mri_dir.exists(),
            },
            "reoriented_dir": {
                "path": str(workspace.reoriented_dir),
                "exists": workspace.reoriented_dir.exists(),
            },
            "hd_bet_dir": {
                "path": str(workspace.hd_bet_dir),
                "exists": workspace.hd_bet_dir.exists(),
            },
            "fast_dir": {
                "path": str(workspace.fast_dir),
                "exists": workspace.fast_dir.exists(),
            },
            "qc_dir": {
                "path": str(workspace.qc_dir),
                "exists": workspace.qc_dir.exists(),
            },
            "mesh_dir": {
                "path": str(workspace.mesh_dir),
                "exists": workspace.mesh_dir.exists(),
            },
        },

        "known_outputs": {
            "reoriented_path": {
                "path": str(workspace.reoriented_path),
                "exists": workspace.reoriented_path.exists(),
            },
            "skull_stripped_path": {
                "path": str(workspace.skull_stripped_path),
                "exists": workspace.skull_stripped_path.exists(),
            },
            "fast_seg_path": {
                "path": str(workspace.fast_seg_path),
                "exists": workspace.fast_seg_path.exists(),
            },
            "metrics_json_path": {
                "path": str(workspace.metrics_json_path),
                "exists": workspace.metrics_json_path.exists(),
            },
        },
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
