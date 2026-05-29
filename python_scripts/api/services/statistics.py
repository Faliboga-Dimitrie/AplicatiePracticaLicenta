from __future__ import annotations

import json
from datetime import date
from typing import Any

from ...access_control import DbResult, MriCaseRecord, UserRecord
from ...mesh_analysis.evolution_in_time import MriEvolutionInTime
from ...project_core.domain import TissueSurfaces, TissueVolumes, validate_acquisition_date
from .cases import CaseService


class StatisticsService:
    """Read mesh-analysis metrics and build subject evolution reports for React."""

    def __init__(self, *, cases: CaseService):
        self.cases = cases

    def metrics_for_case(self, user: UserRecord, case_id: int) -> DbResult[dict[str, Any]]:
        case_result = self.cases.get_for_user(user, case_id, minimum_role="viewer")
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        try:
            return DbResult.ok(self._metrics_payload_for_case(case_result.data))
        except FileNotFoundError:
            return DbResult.ok(None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def evolution_dates_for_subject(self, user: UserRecord, subject_id: str) -> DbResult[dict[str, Any]]:
        cases_result = self.cases.list_for_subject(user, subject_id)
        if not cases_result.success:
            return DbResult.fail(cases_result.error or "Could not load MRI cases.")
        if cases_result.data is None:
            return DbResult.ok(None)

        entries = [self._date_entry(case) for case in cases_result.data]
        entries.sort(key=lambda item: item["acquisition_date"])
        return DbResult.ok(
            {
                "subject_id": subject_id,
                "dates": entries,
            }
        )

    def evolution_report_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        start_date: str,
        end_date: str,
    ) -> DbResult[dict[str, Any]]:
        try:
            start_date = validate_acquisition_date(start_date)
            end_date = validate_acquisition_date(end_date)
        except Exception as exc:
            return DbResult.fail(str(exc))

        cases_result = self.cases.list_for_subject(user, subject_id)
        if not cases_result.success:
            return DbResult.fail(cases_result.error or "Could not load MRI cases.")
        if cases_result.data is None:
            return DbResult.ok(None)

        selected_cases = [
            case
            for case in cases_result.data
            if start_date <= case.acquisition_date.isoformat() <= end_date
        ]
        selected_cases.sort(key=lambda case: case.acquisition_date)

        workspaces = []
        for case in selected_cases:
            workspace = getattr(case, "workspace", None)
            if workspace is not None and workspace.metrics_json_path.exists():
                workspaces.append(workspace)

        if len(workspaces) < 2:
            return DbResult.fail("Time comparison requires at least two metric-ready MRI cases in the selected interval.")

        try:
            evolution = MriEvolutionInTime.from_workspaces(
                start_date=start_date,
                end_date=end_date,
                workspaces=workspaces,
            )
            return DbResult.ok(evolution.build_comparison_json())
        except Exception as exc:
            return DbResult.fail(str(exc))

    def evolution_visual_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        start_date: str,
        end_date: str,
        target_date: str | None = None,
        tissues: list[str] | None = None,
        include_meshes: bool = False,
        include_wireframes: bool = True,
    ) -> DbResult[bytes]:
        try:
            start_date = validate_acquisition_date(start_date)
            end_date = validate_acquisition_date(end_date)
            if target_date is not None:
                target_date = validate_acquisition_date(target_date)
        except Exception as exc:
            return DbResult.fail(str(exc))

        cases_result = self.cases.list_for_subject(user, subject_id)
        if not cases_result.success:
            return DbResult.fail(cases_result.error or "Could not load MRI cases.")
        if cases_result.data is None:
            return DbResult.ok(None)

        selected_cases = [
            case
            for case in cases_result.data
            if start_date <= case.acquisition_date.isoformat() <= end_date
        ]
        selected_cases.sort(key=lambda case: case.acquisition_date)

        workspaces = []
        for case in selected_cases:
            workspace = getattr(case, "workspace", None)
            if workspace is not None:
                workspaces.append(workspace)

        if len(workspaces) < 2:
            return DbResult.fail("Visual comparison requires at least two MRI cases in the selected interval.")

        try:
            evolution = MriEvolutionInTime.from_workspaces(
                start_date=start_date,
                end_date=end_date,
                workspaces=workspaces,
            )
            return DbResult.ok(
                evolution.build_visual_comparison_glb(
                    target_date=target_date,
                    tissues=tissues,
                    include_meshes=include_meshes,
                    include_wireframes=include_wireframes,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    def _metrics_payload_for_case(self, case: MriCaseRecord) -> dict[str, Any]:
        workspace = getattr(case, "workspace", None)
        if workspace is None or not workspace.metrics_json_path.exists():
            raise FileNotFoundError("Metrics JSON does not exist for this case.")

        with workspace.metrics_json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        volumes = TissueVolumes.from_mapping(payload.get("volumes") or {}).to_dict()
        surfaces = TissueSurfaces.from_mapping(payload.get("surfaces") or {}).to_dict()

        total_volume = round(sum(float(value) for value in volumes.values()), 3)
        total_surface = round(sum(float(value) for value in surfaces.values()), 3)

        return {
            "case_id": case.id,
            "case_key": getattr(case, "case_key", None),
            "subject_id": case.subject_id,
            "acquisition_date": case.acquisition_date.isoformat(),
            "status": case.status,
            "volumes": volumes,
            "surfaces": surfaces,
            "totals": {
                "volume_mm3": total_volume,
                "surface_mm2": total_surface,
            },
            "raw": {
                key: value
                for key, value in payload.items()
                if key not in {"mesh_paths", "wireframe_paths"}
            },
        }

    def _date_entry(self, case: MriCaseRecord) -> dict[str, Any]:
        workspace = getattr(case, "workspace", None)
        metrics_ready = bool(workspace is not None and workspace.metrics_json_path.exists())
        mesh_ready = bool(workspace is not None and getattr(workspace, "has_any_mesh_outputs", False))
        wireframe_ready = bool(workspace is not None and getattr(workspace, "has_any_wireframe_outputs", False))
        complete_visual = bool(
            workspace is not None
            and getattr(workspace, "has_complete_mesh_outputs", False)
            and getattr(workspace, "has_complete_wireframe_outputs", False)
        )

        return {
            "case_id": case.id,
            "acquisition_date": case.acquisition_date.isoformat(),
            "status": case.status,
            "ready_for_json": metrics_ready,
            "ready_for_visual": complete_visual,
            "has_metrics": metrics_ready,
            "has_meshes": mesh_ready,
            "has_wireframes": wireframe_ready,
        }


__all__ = ["StatisticsService"]
