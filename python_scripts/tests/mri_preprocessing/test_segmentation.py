from __future__ import annotations

from pathlib import Path

import pytest

from python_scripts.mri_preprocessing.segmentation import FslFastSegmentationBackend


def test_fast_run_returns_existing_pve_outputs_without_running_fast(settings, workspace, tmp_path, monkeypatch):
    # Arrange
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)
    for pve_path in workspace.fast_pve_paths.values():
        pve_path.write_text("pve", encoding="utf-8")

    backend = FslFastSegmentationBackend(settings)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("FAST should not run when complete outputs already exist and skip_existing=True")

    monkeypatch.setattr(backend, "_validate_input", fail_if_called)
    monkeypatch.setattr(backend, "_run_fast", fail_if_called)

    # Act
    result = backend.run(tmp_path / "missing_input_is_not_needed.nii.gz", workspace)

    # Assert
    assert result.pve_paths == workspace.fast_pve_paths


def test_fast_cleanup_removes_unused_outputs_and_keeps_pve_files(settings, workspace):
    # Arrange
    backend = FslFastSegmentationBackend(settings)
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)

    keep_paths = list(workspace.fast_pve_paths.values())
    remove_paths = [
        workspace.fast_dir / f"{workspace.subject_id}_mixeltype.nii.gz",
        workspace.fast_dir / f"{workspace.subject_id}_seg.nii.gz",
        workspace.fast_dir / f"{workspace.subject_id}_pveseg.nii.gz",
    ]

    sibling_case_dir = workspace.fast_dir.parent / "2026-06-03"
    sibling_case_dir.mkdir(parents=True, exist_ok=True)
    sibling_unused = sibling_case_dir / f"{workspace.subject_id}_seg.nii.gz"

    for path in [*keep_paths, *remove_paths, sibling_unused]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    # Act
    backend._fast_cleanup(workspace)

    # Assert
    assert all(path.exists() for path in keep_paths)
    assert all(not path.exists() for path in remove_paths)
    assert not sibling_unused.exists()


def test_fast_run_cleans_unused_files_after_successful_fake_fast(settings, workspace, tmp_path, monkeypatch):
    # Arrange
    backend = FslFastSegmentationBackend(settings)
    input_path = tmp_path / "brain.nii.gz"
    input_path.write_text("fake input", encoding="utf-8")
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)

    def fake_validate(_input_path, _workspace):
        return None

    def fake_run_fast(_input_path, run_workspace):
        for pve_path in run_workspace.fast_pve_paths.values():
            pve_path.write_text("pve", encoding="utf-8")
        (run_workspace.fast_dir / f"{run_workspace.subject_id}_seg.nii.gz").write_text("unused", encoding="utf-8")
        (run_workspace.fast_dir / f"{run_workspace.subject_id}_pveseg.nii.gz").write_text("unused", encoding="utf-8")
        (run_workspace.fast_dir / f"{run_workspace.subject_id}_mixeltype.nii.gz").write_text("unused", encoding="utf-8")

    monkeypatch.setattr(backend, "_validate_input", fake_validate)
    monkeypatch.setattr(backend, "_run_fast", fake_run_fast)

    # Act
    result = backend.run(input_path, workspace)

    # Assert
    assert result.pve_paths == workspace.fast_pve_paths
    assert all(path.exists() for path in workspace.fast_pve_paths.values())
    assert not list(workspace.fast_dir.glob("*_seg.nii.gz"))
    assert not list(workspace.fast_dir.glob("*_pveseg.nii.gz"))
    assert not list(workspace.fast_dir.glob("*_mixeltype.nii.gz"))


def test_fast_run_raises_when_required_pve_outputs_are_missing(settings, workspace, tmp_path, monkeypatch):
    # Arrange
    backend = FslFastSegmentationBackend(settings)
    input_path = tmp_path / "brain.nii.gz"
    input_path.write_text("fake input", encoding="utf-8")
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(backend, "_validate_input", lambda _input_path, _workspace: None)
    monkeypatch.setattr(backend, "_run_fast", lambda _input_path, _workspace: None)

    # Act / Assert
    with pytest.raises(RuntimeError, match="expected output files"):
        backend.run(input_path, workspace)
