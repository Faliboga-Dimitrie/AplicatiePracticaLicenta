from __future__ import annotations

from pathlib import Path

import pytest

from python_scripts.project_core.domain import MRICase, TissueName
from python_scripts.project_core.workspace import (
    FileSystemWorkspaceProvider,
    build_case_workspace,
)


def test_build_case_workspace_creates_canonical_case_paths(settings, tmp_path):
    # Arrange
    case = MRICase(
        subject_id="IXI001",
        acquisition_date="2026-06-02",
        raw_path=tmp_path / "raw_input.nii.gz",
    )

    # Act
    workspace = build_case_workspace(case, settings)

    # Assert
    assert workspace.case_id == "IXI001_2026-06-02"
    assert workspace.input_mri_dir == settings.input_mri_dir / "IXI001" / "2026-06-02"
    assert workspace.raw_path == workspace.input_mri_dir / "raw_input.nii.gz"
    assert workspace.reoriented_path == workspace.reoriented_dir / "IXI001_reo.nii.gz"
    assert workspace.skull_stripped_path == workspace.hd_bet_dir / "IXI001_bet.nii.gz"
    assert workspace.fast_prefix == workspace.fast_dir / "IXI001"
    assert workspace.fast_pve_paths[TissueName.CSF.value].name == "IXI001_pve_0.nii.gz"
    assert workspace.fast_pve_paths[TissueName.GM.value].name == "IXI001_pve_1.nii.gz"
    assert workspace.fast_pve_paths[TissueName.WM.value].name == "IXI001_pve_2.nii.gz"


def test_ensure_input_file_copies_raw_input_and_respects_overwrite(workspace, tmp_path):
    # Arrange
    source = tmp_path / "source.nii.gz"
    source.write_text("original", encoding="utf-8")
    workspace = workspace.__class__(
        **{**workspace.__dict__, "source_raw_path": source, "raw_path": workspace.input_mri_dir / source.name}
    )

    # Act
    workspace.ensure_input_file(overwrite=False)

    # Assert
    assert workspace.raw_path.read_text(encoding="utf-8") == "original"

    # Arrange
    source.write_text("changed", encoding="utf-8")

    # Act
    workspace.ensure_input_file(overwrite=False)

    # Assert
    assert workspace.raw_path.read_text(encoding="utf-8") == "original"

    # Act
    workspace.ensure_input_file(overwrite=True)

    # Assert
    assert workspace.raw_path.read_text(encoding="utf-8") == "changed"


def test_delete_workspace_can_remove_processed_outputs_but_keep_input(workspace):
    # Arrange
    for directory in workspace.stage_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker.txt").write_text("x", encoding="utf-8")

    # Act
    removed = workspace.delete_workspace(include_input=False)

    # Assert
    assert workspace.input_mri_dir.exists()
    assert set(removed) == set(workspace.processed_stage_dirs)
    assert all(not directory.exists() for directory in workspace.processed_stage_dirs)


def test_stage_delete_workspace_can_be_rolled_back_and_committed(settings, workspace):
    # Arrange
    for directory in workspace.stage_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker.txt").write_text("x", encoding="utf-8")

    provider = FileSystemWorkspaceProvider(settings)

    # Act
    staged = workspace.stage_delete_workspace()

    # Assert
    assert len(staged) == len(workspace.stage_dirs)
    assert all(not original.exists() for _backup, original in staged)
    assert all(backup.exists() for backup, _original in staged)

    # Act
    provider.rollback_staged_delete(staged)

    # Assert
    assert all(directory.exists() for directory in workspace.stage_dirs)

    # Act
    staged_again = workspace.stage_delete_workspace()
    removed = provider.commit_staged_delete(staged_again)

    # Assert
    assert set(removed) == set(workspace.stage_dirs)
    assert all(not directory.exists() for directory in workspace.stage_dirs)
    assert all(not backup.exists() for backup, _original in staged_again)


def test_provider_delete_subject_workspaces_removes_all_subject_stage_roots(settings):
    # Arrange
    provider = FileSystemWorkspaceProvider(settings)
    subject_id = "IXI001"
    expected_dirs = [
        settings.input_mri_dir / subject_id,
        settings.reoriented_dir / subject_id,
        settings.hd_bet_dir / subject_id,
        settings.fast_dir / subject_id,
        settings.mesh_dir / subject_id,
    ]
    for directory in expected_dirs:
        (directory / "2026-06-02").mkdir(parents=True, exist_ok=True)

    # Act
    removed = provider.delete_subject_workspaces(subject_id)

    # Assert
    assert set(removed) == set(expected_dirs)
    assert all(not directory.exists() for directory in expected_dirs)


def test_invalid_acquisition_date_is_rejected(tmp_path):
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="Expected ISO format"):
        MRICase(
            subject_id="IXI001",
            acquisition_date="02-06-2026",
            raw_path=tmp_path / "input.nii.gz",
        )
