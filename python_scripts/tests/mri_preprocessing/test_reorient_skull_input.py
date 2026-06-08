from __future__ import annotations

import types
from pathlib import Path

import numpy as np
import pytest

from python_scripts.mri_preprocessing import input_checks
from python_scripts.mri_preprocessing.input_checks import OrientationStatus, check_input_orientation
from python_scripts.mri_preprocessing.reorient import FslReorientationBackend
from python_scripts.mri_preprocessing.skull_strip import HdBetSkullStripBackend
from python_scripts.project_core.domain import MRICase
from python_scripts.project_core.ports import ReorientationResult


class FakeHeader(dict):
    def __init__(self, *, qform_code: int, sform_code: int):
        super().__init__(qform_code=qform_code, sform_code=sform_code)


class FakeNiftiImage:
    def __init__(
        self,
        *,
        shape=(10, 10, 10),
        ndim=3,
        affine=None,
        qform_code=1,
        sform_code=1,
        qform=None,
        sform=None,
    ):
        self.shape = shape
        self.ndim = ndim
        self.affine = np.eye(4) if affine is None else np.asarray(affine, dtype=float)
        self.header = FakeHeader(qform_code=qform_code, sform_code=sform_code)
        self._qform = self.affine if qform is None else qform
        self._sform = self.affine if sform is None else sform

    def get_qform(self, *, coded=False):
        return (self._qform, self.header["qform_code"]) if coded else self._qform

    def get_sform(self, *, coded=False):
        return (self._sform, self.header["sform_code"]) if coded else self._sform


class Orientation:
    def __init__(self, status, message="orientation message"):
        self.status = status
        self.message = message


@pytest.fixture
def existing_case_file(mri_case):
    # Arrange
    mri_case.raw_path.write_text("input", encoding="utf-8")
    return mri_case


def _patch_orientation(monkeypatch, status):
    def fake_check(_case, _settings):
        return Orientation(status=status)

    monkeypatch.setattr("python_scripts.mri_preprocessing.reorient.check_input_orientation", fake_check)


def test_check_input_orientation_reports_missing_file(settings, tmp_path):
    # Arrange
    case = MRICase("IXI001", "2026-06-02", tmp_path / "missing.nii.gz")

    # Act
    result = check_input_orientation(case, settings)

    # Assert
    assert result.status is OrientationStatus.CANNOT_AUTO_REORIENT
    assert not result.ok_for_pipeline
    assert result.requires_manual_review


def test_check_input_orientation_reports_load_failure(settings, mri_case, monkeypatch):
    # Arrange
    mri_case.raw_path.write_text("not nifti", encoding="utf-8")

    def fake_load(_path):
        raise RuntimeError("bad file")

    monkeypatch.setattr(input_checks.nib, "load", fake_load)

    # Act
    result = check_input_orientation(mri_case, settings)

    # Assert
    assert result.status is OrientationStatus.CANNOT_AUTO_REORIENT
    assert "Failed to load" in result.message


def test_check_input_orientation_detects_already_standard(settings, existing_case_file, monkeypatch):
    # Arrange
    settings.mni_template_path.parent.mkdir(parents=True, exist_ok=True)
    settings.mni_template_path.write_text("template", encoding="utf-8")
    image = FakeNiftiImage(qform_code=1, sform_code=1)
    template = FakeNiftiImage(qform_code=1, sform_code=1)
    monkeypatch.setattr(input_checks.nib, "load", lambda path: template if "MNI" in str(path) else image)
    monkeypatch.setattr(input_checks, "aff2axcodes", lambda _affine: ("R", "A", "S"))

    # Act
    result = check_input_orientation(existing_case_file, settings)

    # Assert
    assert result.status is OrientationStatus.ALREADY_STANDARD
    assert result.ok_for_pipeline
    assert result.already_standard


def test_check_input_orientation_allows_reorientation_when_axis_codes_differ(settings, existing_case_file, monkeypatch):
    # Arrange
    settings.mni_template_path.parent.mkdir(parents=True, exist_ok=True)
    settings.mni_template_path.write_text("template", encoding="utf-8")
    image = FakeNiftiImage(qform_code=1, sform_code=0)
    template = FakeNiftiImage(qform_code=1, sform_code=1)
    monkeypatch.setattr(input_checks.nib, "load", lambda path: template if "MNI" in str(path) else image)

    def fake_aff2axcodes(affine):
        return ("L", "P", "S") if affine is image.affine else ("R", "A", "S")

    monkeypatch.setattr(input_checks, "aff2axcodes", fake_aff2axcodes)

    # Act
    result = check_input_orientation(existing_case_file, settings)

    # Assert
    assert result.status is OrientationStatus.CAN_REORIENT
    assert result.ok_for_pipeline
    assert not result.requires_manual_review


def test_check_input_orientation_requires_review_for_bad_shape_or_missing_metadata(settings, existing_case_file, monkeypatch):
    # Arrange
    settings.mni_template_path.parent.mkdir(parents=True, exist_ok=True)
    settings.mni_template_path.write_text("template", encoding="utf-8")
    template = FakeNiftiImage()
    bad_shape = FakeNiftiImage(shape=(10, 10), ndim=2)
    no_codes = FakeNiftiImage(qform_code=0, sform_code=0)
    monkeypatch.setattr(input_checks, "aff2axcodes", lambda _affine: ("R", "A", "S"))

    # Act
    monkeypatch.setattr(input_checks.nib, "load", lambda path: template if "MNI" in str(path) else bad_shape)
    bad_shape_result = check_input_orientation(existing_case_file, settings)
    monkeypatch.setattr(input_checks.nib, "load", lambda path: template if "MNI" in str(path) else no_codes)
    no_codes_result = check_input_orientation(existing_case_file, settings)

    # Assert
    assert bad_shape_result.status is OrientationStatus.NEEDS_REVIEW
    assert no_codes_result.status is OrientationStatus.NEEDS_REVIEW
    assert not bad_shape_result.ok_for_pipeline


def test_check_input_orientation_requires_review_when_qform_and_sform_disagree(settings, existing_case_file, monkeypatch):
    # Arrange
    settings.mni_template_path.parent.mkdir(parents=True, exist_ok=True)
    settings.mni_template_path.write_text("template", encoding="utf-8")
    image = FakeNiftiImage(qform_code=1, sform_code=1, qform="qform", sform="sform")
    template = FakeNiftiImage(qform_code=1, sform_code=1)
    monkeypatch.setattr(input_checks.nib, "load", lambda path: template if "MNI" in str(path) else image)

    def fake_aff2axcodes(affine):
        if affine == "qform":
            return ("L", "A", "S")
        if affine == "sform":
            return ("R", "A", "S")
        return ("R", "A", "S")

    monkeypatch.setattr(input_checks, "aff2axcodes", fake_aff2axcodes)

    # Act
    result = check_input_orientation(existing_case_file, settings)

    # Assert
    assert result.status is OrientationStatus.NEEDS_REVIEW
    assert result.qform_sform_consistent is False


def test_reorientation_returns_existing_output_when_skip_existing(settings, workspace):
    # Arrange
    workspace.reoriented_dir.mkdir(parents=True, exist_ok=True)
    workspace.reoriented_path.write_text("existing", encoding="utf-8")
    backend = FslReorientationBackend(settings)

    # Act
    result = backend.run(MRICase("IXI001", "2026-06-02", workspace.raw_path), workspace)

    # Assert
    assert isinstance(result, ReorientationResult)
    assert result.output_path == workspace.reoriented_path
    assert not result.already_standard


def test_reorientation_existing_output_raises_when_not_overwrite(settings, workspace):
    # Arrange
    settings = type(settings)(**{**settings.__dict__, "skip_existing": False, "overwrite": False})
    workspace.reoriented_dir.mkdir(parents=True, exist_ok=True)
    workspace.reoriented_path.write_text("existing", encoding="utf-8")
    backend = FslReorientationBackend(settings)

    # Act / Assert
    with pytest.raises(FileExistsError):
        backend.run(MRICase("IXI001", "2026-06-02", workspace.raw_path), workspace)


def test_reorientation_copies_input_when_already_standard(settings, workspace, monkeypatch):
    # Arrange
    workspace.input_mri_dir.mkdir(parents=True, exist_ok=True)
    workspace.raw_path.write_text("raw", encoding="utf-8")
    _patch_orientation(monkeypatch, OrientationStatus.ALREADY_STANDARD)
    backend = FslReorientationBackend(settings)

    # Act
    result = backend.run(MRICase("IXI001", "2026-06-02", workspace.raw_path), workspace)

    # Assert
    assert result.already_standard
    assert workspace.reoriented_path.read_text(encoding="utf-8") == "raw"


def test_reorientation_refuses_when_orientation_status_is_not_auto(settings, workspace, monkeypatch):
    # Arrange
    _patch_orientation(monkeypatch, OrientationStatus.NEEDS_REVIEW)
    backend = FslReorientationBackend(settings)

    # Act / Assert
    with pytest.raises(RuntimeError, match="Automatic reorientation refused"):
        backend.run(MRICase("IXI001", "2026-06-02", workspace.raw_path), workspace)


def test_reorientation_post_check_raises_when_output_not_standard(settings, workspace, monkeypatch):
    # Arrange
    backend = FslReorientationBackend(settings)
    _patch_orientation(monkeypatch, OrientationStatus.NEEDS_REVIEW)

    # Act / Assert
    with pytest.raises(RuntimeError, match="output still does not match"):
        backend._check_output_is_standard(MRICase("IXI001", "2026-06-02", workspace.raw_path), workspace)


def test_hd_bet_build_command_validates_device_and_adds_disable_tta(settings, tmp_path, monkeypatch):
    # Arrange
    backend = HdBetSkullStripBackend(settings)
    monkeypatch.setattr(backend, "_supports_flag", lambda _exe, flag: flag == "--disable_tta")

    # Act
    command = backend._build_command(exe="hd-bet", input_path=tmp_path / "input.nii.gz", output_path=tmp_path / "bet.nii.gz")

    # Assert
    assert command[:5] == ["hd-bet", "-i", str(tmp_path / "input.nii.gz"), "-o", str(tmp_path / "bet.nii.gz")]
    assert "-device" in command
    assert "cpu" in command
    assert "--disable_tta" in command
    assert "--verbose" in command

    bad_settings = type(settings)(**{**settings.__dict__, "hd_bet_device": "gpu"})
    with pytest.raises(ValueError):
        HdBetSkullStripBackend(bad_settings)._build_command(exe="hd-bet", input_path=tmp_path / "in.nii.gz", output_path=tmp_path / "out.nii.gz")


def test_hd_bet_existing_output_skip_and_overwrite_paths(settings, workspace):
    # Arrange
    workspace.hd_bet_dir.mkdir(parents=True, exist_ok=True)
    workspace.skull_stripped_path.write_text("existing", encoding="utf-8")
    backend = HdBetSkullStripBackend(settings)

    # Act
    skipped = backend._handle_existing_outputs(workspace=workspace, output_path=workspace.skull_stripped_path)

    # Assert
    assert skipped is not None
    assert skipped.image_path == workspace.skull_stripped_path

    no_overwrite_settings = type(settings)(**{**settings.__dict__, "skip_existing": False, "overwrite": False})
    with pytest.raises(FileExistsError):
        HdBetSkullStripBackend(no_overwrite_settings)._handle_existing_outputs(workspace=workspace, output_path=workspace.skull_stripped_path)

    overwrite_settings = type(settings)(**{**settings.__dict__, "skip_existing": False, "overwrite": True})
    assert HdBetSkullStripBackend(overwrite_settings)._handle_existing_outputs(workspace=workspace, output_path=workspace.skull_stripped_path) is None
    assert not workspace.skull_stripped_path.exists()


def test_hd_bet_validate_input_checks_exists_and_3d(settings, tmp_path, monkeypatch):
    # Arrange
    backend = HdBetSkullStripBackend(settings)
    input_path = tmp_path / "input.nii.gz"
    input_path.write_text("nifti", encoding="utf-8")

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        backend._validate_input(tmp_path / "missing.nii.gz")

    monkeypatch.setattr("python_scripts.mri_preprocessing.skull_strip.nib.load", lambda _path: types.SimpleNamespace(ndim=4))
    with pytest.raises(ValueError):
        backend._validate_input(input_path)

    monkeypatch.setattr("python_scripts.mri_preprocessing.skull_strip.nib.load", lambda _path: types.SimpleNamespace(ndim=3))
    backend._validate_input(input_path)


def test_hd_bet_run_success_and_failure_without_real_executable(settings, workspace, tmp_path, monkeypatch):
    # Arrange
    input_path = tmp_path / "input.nii.gz"
    input_path.write_text("input", encoding="utf-8")
    backend = HdBetSkullStripBackend(settings)
    monkeypatch.setattr(backend, "_ensure_hd_bet_available", lambda: "hd-bet")
    monkeypatch.setattr(backend, "_validate_input", lambda _path: None)

    def successful_run(_cmd, **_kwargs):
        workspace.hd_bet_dir.mkdir(parents=True, exist_ok=True)
        workspace.skull_stripped_path.write_text("bet", encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("python_scripts.mri_preprocessing.skull_strip.subprocess.run", successful_run)

    # Act
    result = backend.run(input_path, workspace)

    # Assert
    assert result.image_path == workspace.skull_stripped_path

    workspace.skull_stripped_path.unlink()
    monkeypatch.setattr(
        "python_scripts.mri_preprocessing.skull_strip.subprocess.run",
        lambda *_args, **_kwargs: types.SimpleNamespace(returncode=1, stdout="out", stderr="err"),
    )
    with pytest.raises(RuntimeError, match="HD-BET failed"):
        backend.run(input_path, workspace)
