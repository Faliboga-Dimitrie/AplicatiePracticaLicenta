from __future__ import annotations

from pathlib import Path

import pytest

from python_scripts.project_core.artifacts import (
    ArtifactKind,
    ArtifactRef,
    guess_mime_type,
    normalize_artifact_kind,
)
from python_scripts.project_core.domain import (
    MRICase,
    MeshAnalysisResult,
    TissueSurfaces,
    TissueVolumes,
    strip_nii_suffix,
    tissue_key,
    validate_acquisition_date,
)


def test_tissue_and_nifti_helpers_normalize_expected_values():
    # Arrange / Act / Assert
    assert tissue_key(" GM ") == "gm"
    assert strip_nii_suffix(Path("subject.nii.gz")) == "subject"
    assert strip_nii_suffix(Path("subject.nii")) == "subject"
    assert strip_nii_suffix(Path("subject.other")) == "subject"
    assert validate_acquisition_date(" 2026-06-02 ") == "2026-06-02"


@pytest.mark.parametrize("bad_date", ["2026/06/02", "not-a-date", "2026-02-30"])
def test_validate_acquisition_date_rejects_non_iso_dates(bad_date):
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        validate_acquisition_date(bad_date)


def test_mri_case_normalizes_raw_path_and_builds_case_id(tmp_path):
    # Arrange
    raw_path = tmp_path / "raw.nii.gz"

    # Act
    case = MRICase(subject_id="IXI001", acquisition_date=" 2026-06-02 ", raw_path=raw_path)

    # Assert
    assert case.acquisition_date == "2026-06-02"
    assert case.raw_path == raw_path
    assert case.case_id == "IXI001_2026-06-02"


def test_metric_models_support_dict_and_tissue_key_mappings():
    # Arrange / Act
    volumes = TissueVolumes.from_mapping({"csf": 1, "gm": "2.5", "wm_mm3": 3})
    surfaces = TissueSurfaces.from_mapping({"csf_mm2": 4, "gm": 5, "wm": "6.5"})

    # Assert
    assert volumes.to_dict() == {"csf_mm3": 1.0, "gm_mm3": 2.5, "wm_mm3": 3.0}
    assert volumes.as_tissue_dict() == {"csf": 1.0, "gm": 2.5, "wm": 3.0}
    assert surfaces.to_dict() == {"csf_mm2": 4.0, "gm_mm2": 5.0, "wm_mm2": 6.5}
    assert surfaces.as_tissue_dict() == {"csf": 4.0, "gm": 5.0, "wm": 6.5}


def test_mesh_analysis_result_serializes_optional_acquisition_date():
    # Arrange
    result = MeshAnalysisResult(
        subject_id="IXI001",
        acquisition_date="2026-06-02",
        volumes=TissueVolumes(1, 2, 3),
        surfaces=TissueSurfaces(4, 5, 6),
    )

    # Act
    payload = result.to_dict()

    # Assert
    assert result.case_id == "IXI001_2026-06-02"
    assert payload["acquisition_date"] == "2026-06-02"
    assert payload["volumes"] == {"csf_mm3": 1, "gm_mm3": 2, "wm_mm3": 3}
    assert payload["surfaces"] == {"csf_mm2": 4, "gm_mm2": 5, "wm_mm2": 6}


def test_mesh_analysis_result_without_date_remains_backward_compatible():
    # Arrange
    result = MeshAnalysisResult(
        subject_id="IXI001",
        volumes=TissueVolumes(1, 2, 3),
        surfaces=TissueSurfaces(4, 5, 6),
    )

    # Act
    payload = result.to_dict()

    # Assert
    assert result.case_id == "IXI001"
    assert "case_id" not in payload
    assert "acquisition_date" not in payload


def test_artifact_ref_serializes_optional_fields_and_normalizes_kind(tmp_path):
    # Arrange
    path = tmp_path / "mesh.glb"

    # Act
    ref = ArtifactRef.from_path(
        name="gm mesh",
        kind="mesh",
        path=path,
        mime_type="model/gltf-binary",
        metadata={"tissue": "gm"},
    )

    # Assert
    assert ref.kind is ArtifactKind.MESH
    assert ref.to_dict() == {
        "name": "gm mesh",
        "kind": "mesh",
        "uri": str(path),
        "mime_type": "model/gltf-binary",
        "metadata": {"tissue": "gm"},
    }


def test_artifact_kind_and_mime_type_helpers_cover_only_published_outputs():
    # Arrange / Act / Assert
    assert normalize_artifact_kind(ArtifactKind.MESH) is ArtifactKind.MESH
    assert normalize_artifact_kind("metrics") is ArtifactKind.METRICS
    assert guess_mime_type(Path("brain.glb")) == "model/gltf-binary"
    assert guess_mime_type(Path("metrics.json")) == "application/json"
    assert guess_mime_type(Path("scene.gltf")) is None
    assert guess_mime_type(Path("plot.png")) is None
    assert guess_mime_type(Path("photo.jpeg")) is None
    assert guess_mime_type(Path("scan.nii.gz")) is None
    assert guess_mime_type(Path("log.txt")) is None

    with pytest.raises(ValueError):
        normalize_artifact_kind("nifti")

    with pytest.raises(ValueError):
        normalize_artifact_kind("unknown")
