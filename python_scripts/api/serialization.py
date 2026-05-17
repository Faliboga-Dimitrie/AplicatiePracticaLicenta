from __future__ import annotations

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