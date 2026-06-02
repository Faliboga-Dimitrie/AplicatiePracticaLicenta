from __future__ import annotations

import pytest

from python_scripts.project_core.domain import MRICase
from python_scripts.project_core.workspace import FileSystemWorkspaceProvider, build_case_workspace


def _case(subject_id: str, date: str, raw_path):
    return MRICase(subject_id=subject_id, acquisition_date=date, raw_path=raw_path)


def test_ensure_directories_creates_all_stage_directories(workspace):
    # Arrange / Act
    workspace.ensure_directories()

    # Assert
    assert all(directory.exists() and directory.is_dir() for directory in workspace.stage_dirs)


def test_ensure_input_file_noops_when_source_is_already_canonical(workspace):
    # Arrange
    workspace.input_mri_dir.mkdir(parents=True, exist_ok=True)
    workspace.raw_path.write_text("canonical", encoding="utf-8")
    canonical_workspace = type(workspace)(
        subject_id=workspace.subject_id,
        acquisition_date=workspace.acquisition_date,
        source_raw_path=workspace.raw_path,
        raw_path=workspace.raw_path,
        input_mri_dir=workspace.input_mri_dir,
        reoriented_dir=workspace.reoriented_dir,
        hd_bet_dir=workspace.hd_bet_dir,
        fast_dir=workspace.fast_dir,
        mesh_dir=workspace.mesh_dir,
    )

    # Act
    canonical_workspace.ensure_input_file(overwrite=True)

    # Assert
    assert workspace.raw_path.read_text(encoding="utf-8") == "canonical"


def test_ensure_input_file_rejects_missing_or_directory_sources(settings, tmp_path):
    # Arrange
    missing_workspace = build_case_workspace(_case("IXI001", "2026-06-02", tmp_path / "missing.nii.gz"), settings)
    directory_source = tmp_path / "source_dir"
    directory_source.mkdir()
    directory_workspace = build_case_workspace(_case("IXI001", "2026-06-03", directory_source), settings)

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        missing_workspace.ensure_input_file()
    with pytest.raises(ValueError):
        directory_workspace.ensure_input_file()


def test_fast_and_mesh_completion_flags_reflect_existing_outputs(workspace):
    # Arrange
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)
    workspace.mesh_dir.mkdir(parents=True, exist_ok=True)

    # Act / Assert
    assert not workspace.has_fast_pve_outputs
    assert len(workspace.missing_fast_pve_paths) == 3
    for path in workspace.fast_pve_paths.values():
        path.write_text("pve", encoding="utf-8")
    assert workspace.has_fast_pve_outputs
    assert workspace.missing_fast_pve_paths == []

    assert not workspace.has_any_mesh_analysis_outputs
    assert not workspace.has_complete_mesh_analysis_outputs
    first_mesh = next(iter(workspace.mesh_paths.values()))
    first_mesh.write_text("mesh", encoding="utf-8")
    assert workspace.has_any_mesh_analysis_outputs
    assert not workspace.has_complete_mesh_analysis_outputs
    for path in workspace.mesh_analysis_output_paths:
        path.write_text("output", encoding="utf-8")
    assert workspace.has_complete_mesh_analysis_outputs


def test_delete_workspace_raises_when_expected_directory_is_a_file(workspace):
    # Arrange
    workspace.input_mri_dir.parent.mkdir(parents=True, exist_ok=True)
    workspace.input_mri_dir.write_text("not a directory", encoding="utf-8")

    # Act / Assert
    with pytest.raises(ValueError):
        workspace.delete_workspace()


def test_rename_to_moves_existing_stage_directories_and_prunes_empty_subject(settings, tmp_path):
    # Arrange
    old_workspace = build_case_workspace(_case("Subject/One", "2026-06-02", tmp_path / "raw.nii.gz"), settings)
    new_workspace = build_case_workspace(_case("Subject/One", "2026-06-03", tmp_path / "raw.nii.gz"), settings)
    old_workspace.ensure_directories()
    old_workspace.fast_dir.joinpath("marker.txt").write_text("fast", encoding="utf-8")

    # Act
    moved = old_workspace.rename_to(new_workspace)

    # Assert
    assert len(moved) == len(old_workspace.stage_dirs)
    assert not old_workspace.fast_dir.exists()
    assert new_workspace.fast_dir.joinpath("marker.txt").read_text(encoding="utf-8") == "fast"
    assert old_workspace.fast_dir.parent != new_workspace.fast_dir.parent or new_workspace.fast_dir.parent.exists()


def test_rename_to_rejects_different_subject_and_existing_target(settings, tmp_path):
    # Arrange
    old_workspace = build_case_workspace(_case("IXI001", "2026-06-02", tmp_path / "raw.nii.gz"), settings)
    different_subject = build_case_workspace(_case("IXI002", "2026-06-03", tmp_path / "raw.nii.gz"), settings)
    target_workspace = build_case_workspace(_case("IXI001", "2026-06-03", tmp_path / "raw.nii.gz"), settings)
    old_workspace.input_mri_dir.mkdir(parents=True)
    target_workspace.input_mri_dir.mkdir(parents=True)

    # Act / Assert
    with pytest.raises(ValueError):
        old_workspace.rename_to(different_subject)
    with pytest.raises(FileExistsError):
        old_workspace.rename_to(target_workspace, overwrite=False)


def test_rename_to_overwrites_target_when_requested(settings, tmp_path):
    # Arrange
    old_workspace = build_case_workspace(_case("IXI001", "2026-06-02", tmp_path / "raw.nii.gz"), settings)
    target_workspace = build_case_workspace(_case("IXI001", "2026-06-03", tmp_path / "raw.nii.gz"), settings)
    old_workspace.input_mri_dir.mkdir(parents=True)
    old_workspace.input_mri_dir.joinpath("raw.nii.gz").write_text("old", encoding="utf-8")
    target_workspace.input_mri_dir.mkdir(parents=True)
    target_workspace.input_mri_dir.joinpath("stale.nii.gz").write_text("target", encoding="utf-8")

    # Act
    moved = old_workspace.rename_to(target_workspace, overwrite=True)

    # Assert
    assert moved == [(old_workspace.input_mri_dir, target_workspace.input_mri_dir)]
    assert target_workspace.input_mri_dir.joinpath("raw.nii.gz").read_text(encoding="utf-8") == "old"
    assert not target_workspace.input_mri_dir.joinpath("stale.nii.gz").exists()


def test_provider_create_workspace_can_skip_directory_creation(settings, mri_case):
    # Arrange
    provider = FileSystemWorkspaceProvider(settings, create_directories=False)

    # Act
    workspace = provider.create_workspace(mri_case)

    # Assert
    assert not any(directory.exists() for directory in workspace.stage_dirs)


def test_provider_stages_and_rolls_back_subject_workspaces(settings):
    # Arrange
    provider = FileSystemWorkspaceProvider(settings)
    for directory in provider._subject_workspace_dirs("Subject/One"):
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath("marker.txt").write_text("data", encoding="utf-8")

    # Act
    staged = provider.stage_subject_workspaces_delete("Subject/One")
    provider.rollback_staged_delete(staged)

    # Assert
    for directory in provider._subject_workspace_dirs("Subject/One"):
        assert directory.joinpath("marker.txt").exists()
