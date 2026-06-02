from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from python_scripts.access_control import DbResult, MriCaseRecord, SubjectRecord, SubjectSummaryRecord, SubjectWithCases, UserRecord
from python_scripts.access_control.utils import UNSET
from python_scripts.api.serialization import (
    artifact_to_dict,
    case_artifacts_to_dict,
    case_capabilities_to_dict,
    job_to_dict,
    mri_case_to_dict,
    subject_summary_to_dict,
    subject_to_dict,
    subject_with_cases_to_dict,
    workspace_to_dict,
)
from python_scripts.api.services.artifacts import ArtifactFile, ArtifactService, CaseArtifactBundle
from python_scripts.api.services.cases import CaseService
from python_scripts.api.services.jobs import JobRecord, JobStatus
from python_scripts.api.services.subjects import SubjectService
from python_scripts.api.services.statistics import StatisticsService
from python_scripts.project_core.artifacts import ArtifactKind, ArtifactRef
from python_scripts.project_core.domain import MRICase, TissueSurfaces, TissueVolumes
from python_scripts.project_core.workspace import build_case_workspace


class FakeAccessForApi:
    def __init__(self, *, allowed_subject=True, allowed_case=True):
        self.allowed_subject = allowed_subject
        self.allowed_case = allowed_case
        self.user = UserRecord(1, "user@example.com")
        self.subject = SubjectRecord("IXI001", "Alice", 20, None)
        self.case = MriCaseRecord(5, "IXI001", date(2026, 6, 2), "n", "registered")
        self.updated_statuses = []
        self.created_cases = []
        self.deleted_cases = []
        self.created_subjects = []
        self.granted_access = []
        self.deleted_subjects = []

    def list_accessible_subjects(self, user_id, *, include_cases=True):
        return DbResult.ok([SubjectWithCases(self.subject, (self.case,) if include_cases else tuple())])

    def list_accessible_subject_summaries(self, user_id):
        return DbResult.ok([SubjectSummaryRecord(self.subject, case_count=1)])

    def search_by_subject_id(self, user_id, subject_id, *, include_cases=True):
        if subject_id != self.subject.id or not self.allowed_subject:
            return DbResult.ok([])
        cases = (self.case,) if include_cases and self.case.subject_id == subject_id else tuple()
        return DbResult.ok([SubjectWithCases(self.subject, cases)])

    def user_has_subject_access(self, user_id, subject_id):
        return DbResult.ok(self.allowed_subject and subject_id == self.subject.id)

    def user_has_case_access(self, user_id, case_id):
        return DbResult.ok(self.allowed_case and case_id == self.case.id)

    def list_cases_for_subject(self, subject_id):
        return DbResult.ok([self.case] if subject_id == self.subject.id else [])

    def get_mri_case(self, case_id):
        return DbResult.ok(self.case if case_id == self.case.id else None)

    def get_mri_case_by_subject_date(self, subject_id, acquisition_date):
        acq = acquisition_date if isinstance(acquisition_date, date) else date.fromisoformat(str(acquisition_date))
        return DbResult.ok(self.case if subject_id == self.case.subject_id and acq == self.case.acquisition_date else None)

    def create_mri_case(self, **kwargs):
        self.created_cases.append(kwargs)
        self.case = MriCaseRecord(6, kwargs["subject_id"], date.fromisoformat(str(kwargs["acquisition_date"])), kwargs.get("notes"), kwargs.get("status"))
        return DbResult.ok(self.case)

    def update_mri_case_by_subject_date(self, subject_id, acquisition_date, *, new_acquisition_date=UNSET, notes=UNSET, status=UNSET):
        self.updated_statuses.append((subject_id, acquisition_date, new_acquisition_date, notes, status))
        new_date = self.case.acquisition_date if new_acquisition_date is UNSET else date.fromisoformat(str(new_acquisition_date))
        self.case = MriCaseRecord(self.case.id, subject_id, new_date, self.case.notes if notes is UNSET else notes, self.case.status if status is UNSET else status, self.case.workspace)
        return DbResult.ok(True)

    def delete_mri_case_by_subject_date(self, subject_id, acquisition_date):
        self.deleted_cases.append((subject_id, acquisition_date))
        return DbResult.ok(True)

    def get_subject(self, subject_id):
        return DbResult.ok(self.subject if subject_id == self.subject.id else None)

    def get_subject_access(self, user_id, subject_id):
        return DbResult.ok(object() if self.allowed_subject and subject_id == self.subject.id else None)

    def create_subject(self, subject_id, *, name=None, age=None, notes=None):
        self.created_subjects.append(subject_id)
        self.subject = SubjectRecord(subject_id, name, age, notes)
        return DbResult.ok(self.subject)

    def grant_subject_access(self, user_id, subject_id):
        self.granted_access.append((user_id, subject_id))
        return DbResult.ok(True)

    def update_subject_for_user(self, user_id, subject_id, **kwargs):
        return DbResult.ok(self.allowed_subject)

    def delete_subject_for_user(self, user_id, subject_id):
        self.deleted_subjects.append(subject_id)
        return DbResult.ok(self.allowed_subject)

    def delete_subject(self, subject_id):
        self.deleted_subjects.append(subject_id)
        return DbResult.ok(True)


def test_case_service_authorizes_listing_get_create_update_delete_and_status():
    # Arrange
    access = FakeAccessForApi()
    user = access.user
    service = CaseService(access)
    raw_path = Path("scan.nii.gz")

    # Act
    all_cases = service.list_for_user(user)
    subject_cases = service.list_for_subject(user, "IXI001")
    loaded = service.get_for_user(user, 5)
    missing_raw = service.create_for_user(user, subject_id="IXI001", acquisition_date="2026-06-03")
    created = service.create_for_user(user, subject_id="IXI001", acquisition_date="2026-06-03", source_raw_path=raw_path)
    updated = service.update_for_user(user, 6, notes="updated")
    same_status = service.set_status_for_user(user, 6, access.case.status)
    changed_status = service.set_status_for_user(user, 6, "preprocessed")
    deleted = service.delete_for_user(user, 6)

    # Assert
    assert [case.id for case in all_cases.data] == [5]
    assert subject_cases.data[0].subject_id == "IXI001"
    assert loaded.data.id == 5
    assert missing_raw.success is False
    assert created.data.id == 6
    assert updated.data.notes == "updated"
    assert same_status.data.status == "registered"
    assert changed_status.data.status == "preprocessed"
    assert deleted.data.id == 6


def test_case_service_returns_none_when_user_has_no_access():
    # Arrange
    access = FakeAccessForApi(allowed_subject=False, allowed_case=False)
    user = access.user
    service = CaseService(access)

    # Act / Assert
    assert service.list_for_subject(user, "IXI001").data is None
    assert service.get_for_user(user, 5).data is None
    assert service.get_by_subject_date(user, "IXI001", "2026-06-02").data is None


def test_subject_service_creates_subject_grants_access_and_rolls_back_on_grant_failure():
    # Arrange
    access = FakeAccessForApi()
    access.subject = SubjectRecord("OTHER", None, None, None)
    service = SubjectService(access)
    user = access.user

    # Act
    created = service.create_for_user(user, subject_id="NEW", name="New")
    summaries = service.list_summaries_for_user(user)
    loaded = service.get_for_user(user, "NEW", include_cases=False)
    cases = service.list_cases_for_subject(user, "NEW")
    updated = service.update_subject_for_user(user, "NEW", name="Renamed")
    deleted = service.delete_for_user(user, "NEW")

    # Assert
    assert created.success is True
    assert access.granted_access == [(1, "NEW")]
    assert summaries.data[0].case_count == 1
    assert loaded.data.subject.id == "NEW"
    assert cases.data == []
    assert updated.data is True
    assert deleted.data is True


def test_subject_service_rejects_existing_visible_or_claimed_subjects():
    # Arrange
    access = FakeAccessForApi(allowed_subject=True)
    service = SubjectService(access)
    user = access.user

    # Act
    visible = service.create_for_user(user, subject_id="IXI001")
    access.allowed_subject = False
    claimed = service.create_for_user(user, subject_id="IXI001")

    # Assert
    assert visible.success is False
    assert "already visible" in visible.error
    assert claimed.success is False
    assert "linked to another account" in claimed.error


def test_workspace_and_case_serialization_report_outputs_and_capabilities(workspace):
    # Arrange
    workspace.ensure_directories()
    workspace.raw_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.raw_path.write_text("raw")
    workspace.reoriented_path.write_text("reo")
    workspace.skull_stripped_path.write_text("bet")
    for path in workspace.fast_pve_paths.values():
        path.write_text("pve")
    workspace.metrics_json_path.write_text("{}")
    workspace.mesh_path_for("csf").write_text("mesh")
    case = MriCaseRecord(5, workspace.subject_id, date.fromisoformat(workspace.acquisition_date), None, "preprocessed", workspace)

    # Act
    workspace_payload = workspace_to_dict(workspace)
    case_payload = mri_case_to_dict(case)
    capabilities = case_capabilities_to_dict(case)

    # Assert
    assert workspace_payload["outputs"]["fast_pve_outputs"] is True
    assert case_payload["case_key"] == "IXI001_2026-06-02"
    assert capabilities["raw_uploaded"] is True
    assert capabilities["can_start_mesh_analysis"] is True
    assert capabilities["can_view_artifacts"] is True


def test_subject_artifact_and_job_serializers_are_frontend_safe():
    # Arrange
    subject = SubjectRecord("IXI001", "Alice", 20, "notes")
    case = MriCaseRecord(5, "IXI001", date(2026, 6, 2), None, "registered")
    bundle = CaseArtifactBundle(
        case_db_id=5,
        subject_id="IXI001",
        acquisition_date=date(2026, 6, 2),
        case_key="IXI001_2026-06-02",
        artifacts=(ArtifactFile(ArtifactRef("metrics.json", ArtifactKind.METRICS, "/cases/5/artifacts/metrics.json", metadata={"p": Path("x")}), Path("metrics.json"), 10),),
    )
    job = JobRecord(id="j", type="t", status=JobStatus.COMPLETED, user_id=1, case_id=5, result={"date": date(2026, 6, 2), "path": Path("x")})

    # Act
    subject_payload = subject_to_dict(subject)
    summary_payload = subject_summary_to_dict(SubjectSummaryRecord(subject, 2))
    with_cases_payload = subject_with_cases_to_dict(SubjectWithCases(subject, (case,)))
    artifact_payload = artifact_to_dict(bundle.artifacts[0])
    bundle_payload = case_artifacts_to_dict(bundle)
    job_payload = job_to_dict(job)

    # Assert
    assert subject_payload["name"] == "Alice"
    assert summary_payload["case_count"] == 2
    assert with_cases_payload["cases"][0]["id"] == 5
    assert artifact_payload["metadata"]["p"] == "x"
    assert bundle_payload["artifacts"][0]["name"] == "metrics.json"
    assert job_payload["result"]["date"] == "2026-06-02"


def test_artifact_service_lists_only_existing_artifacts_and_filters_viewer_files(workspace):
    # Arrange
    workspace.ensure_directories()
    workspace.mesh_path_for("csf").write_bytes(b"glb")
    workspace.metrics_json_path.write_text("{}")
    workspace.reoriented_path.write_text("reo")
    case = MriCaseRecord(5, workspace.subject_id, date.fromisoformat(workspace.acquisition_date), None, "completed", workspace)
    cases = Mock()
    cases.get_for_user.return_value = DbResult.ok(case)
    provider = Mock()
    service = ArtifactService(cases=cases, workspace_provider=provider)
    user = UserRecord(1, "user@example.com")

    # Act
    bundle = service.list_for_case(user, 5)
    viewer = service.list_viewer_for_case(user, 5)
    file_result = service.get_file_for_case(user, 5, "metrics.json")
    missing = service.get_file_for_case(user, 5, "unknown.txt")
    public = service.public_bundle_dict(bundle.data)

    # Assert
    names = [artifact.ref.name for artifact in bundle.data.artifacts]
    assert "csf_mesh.glb" in names
    assert "metrics.json" in names
    assert "reoriented.nii.gz" in names
    assert all(a.ref.kind in {ArtifactKind.MESH, ArtifactKind.METRICS} for a in viewer.data.artifacts)
    assert file_result.data.ref.name == "metrics.json"
    assert missing.data is None
    assert public["artifacts"][0]["url"].startswith("/cases/5/artifacts/")


def test_artifact_service_builds_workspace_when_case_has_no_workspace(workspace):
    # Arrange
    workspace.ensure_directories()
    workspace.metrics_json_path.write_text("{}")
    case = MriCaseRecord(5, workspace.subject_id, date.fromisoformat(workspace.acquisition_date), None, "completed", None)
    cases = Mock(get_for_user=Mock(return_value=DbResult.ok(case)))
    provider = Mock(get_workspace=Mock(return_value=workspace))
    service = ArtifactService(cases=cases, workspace_provider=provider)

    # Act
    result = service.list_for_case(UserRecord(1, "u@e.ro"), 5)

    # Assert
    assert result.success is True
    provider.get_workspace.assert_called_once()
    assert result.data.case_key == workspace.case_id


def test_statistics_service_loads_metrics_and_date_readiness(workspace):
    # Arrange
    workspace.ensure_directories()
    workspace.metrics_json_path.write_text('{"volumes":{"csf":1,"gm":2,"wm":3},"surfaces":{"csf":4,"gm":5,"wm":6},"mesh_paths":{"local":"hidden"}}')
    for path in workspace.fast_pve_paths.values():
        path.write_text("pve")
    case = MriCaseRecord(5, workspace.subject_id, date.fromisoformat(workspace.acquisition_date), None, "completed", workspace)
    cases = Mock()
    cases.get_for_user.return_value = DbResult.ok(case)
    cases.list_for_subject.return_value = DbResult.ok([case])
    service = StatisticsService(cases=cases)
    user = UserRecord(1, "u@e.ro")

    # Act
    metrics = service.metrics_for_case(user, 5)
    dates = service.evolution_dates_for_subject(user, workspace.subject_id)

    # Assert
    assert metrics.data["totals"]["volume_mm3"] == 6.0
    assert "mesh_paths" not in metrics.data["raw"]
    assert dates.data["dates"][0]["ready_for_json"] is True
    assert dates.data["dates"][0]["has_pve_outputs"] is True


def test_statistics_service_interval_helper_filters_by_date_and_metrics(workspace, settings):
    # Arrange
    ws2 = build_case_workspace(MRICase("IXI001", "2026-06-03", workspace.raw_path), settings)
    ws2.ensure_directories()
    workspace.ensure_directories()
    workspace.metrics_json_path.write_text("{}")
    cases = Mock()
    cases.list_for_subject.return_value = DbResult.ok([
        MriCaseRecord(1, "IXI001", date(2026, 6, 1), None, None, None),
        MriCaseRecord(2, "IXI001", date(2026, 6, 2), None, None, workspace),
        MriCaseRecord(3, "IXI001", date(2026, 6, 3), None, None, ws2),
    ])
    service = StatisticsService(cases=cases)

    # Act
    with_metrics = service._comparison_workspaces_for_interval(user=UserRecord(1, "u@e.ro"), subject_id="IXI001", start_date="2026-06-02", end_date="2026-06-03", require_metrics=True)
    without_metrics = service._comparison_workspaces_for_interval(user=UserRecord(1, "u@e.ro"), subject_id="IXI001", start_date="2026-06-02", end_date="2026-06-03", require_metrics=False)

    # Assert
    assert with_metrics.data[2] == [workspace]
    assert without_metrics.data[2] == [workspace, ws2]
