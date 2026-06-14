from __future__ import annotations

import json
from typing import Any

from ...access_control import DbResult, MriCaseRecord, UserRecord
from ...mesh_analysis.evolution_in_time import MriEvolutionInTime
from ...project_core import CaseWorkspace
from ...project_core.domain import TissueSurfaces, TissueVolumes, validate_acquisition_date
from .cases import CaseService


class StatisticsService:
    """Read mesh-analysis metrics and build subject evolution reports for React."""

    def __init__(self, *, cases: CaseService):
        self.cases = cases

    def metrics_for_case(self, user: UserRecord, case_id: int) -> DbResult[dict[str, Any]]:
        case_result = self.cases.get_for_user(user, case_id)
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
        selection = self._comparison_workspaces_for_interval(
            user=user,
            subject_id=subject_id,
            start_date=start_date,
            end_date=end_date,
            require_metrics=True,
        )
        if not selection.success:
            return DbResult.fail(selection.error or "Could not select comparison workspaces.")
        if selection.data is None:
            return DbResult.ok(None)

        normalized_start_date, normalized_end_date, workspaces = selection.data
        if len(workspaces) < 2:
            return DbResult.fail("Time comparison requires at least two metric-ready MRI cases in the selected interval.")

        try:
            evolution = MriEvolutionInTime.from_workspaces(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
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
        comparison_method: str = "pve",
        pve_threshold: float = 0.2,
        distance_threshold_mm: float = 1.0,
        baseline_color: str = "#508cff",
        changed_color: str = "#ff2d2d",
        marching_cubes_step_size: int = 1,
        visual_mode: str = "changed_unchanged",
        visual_style: str = "binary",
    ) -> DbResult[bytes]:
        try:
            normalized_target_date = (
                validate_acquisition_date(target_date)
                if target_date is not None
                else None
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

        selection = self._comparison_workspaces_for_interval(
            user=user,
            subject_id=subject_id,
            start_date=start_date,
            end_date=end_date,
            require_metrics=False,
        )
        if not selection.success:
            return DbResult.fail(selection.error or "Could not select comparison workspaces.")
        if selection.data is None:
            return DbResult.ok(None)

        normalized_start_date, normalized_end_date, workspaces = selection.data
        if len(workspaces) < 2:
            return DbResult.fail("Visual comparison requires at least two MRI cases in the selected interval.")

        try:
            evolution = MriEvolutionInTime.from_workspaces(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
                workspaces=workspaces,
            )
            return DbResult.ok(
                evolution.build_visual_comparison_glb(
                    target_date=normalized_target_date,
                    tissues=tissues,
                    comparison_method=comparison_method,
                    pve_threshold=pve_threshold,
                    distance_threshold_mm=distance_threshold_mm,
                    baseline_color=baseline_color,
                    changed_color=changed_color,
                    marching_cubes_step_size=marching_cubes_step_size,
                    visual_mode=visual_mode,
                    visual_style=visual_style,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    def _comparison_workspaces_for_interval(
        self,
        *,
        user: UserRecord,
        subject_id: str,
        start_date: str,
        end_date: str,
        require_metrics: bool,
    ) -> DbResult[tuple[str, str, list[CaseWorkspace]]]:
        try:
            normalized_start_date = validate_acquisition_date(start_date)
            normalized_end_date = validate_acquisition_date(end_date)
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
            if normalized_start_date <= case.acquisition_date.isoformat() <= normalized_end_date
        ]
        selected_cases.sort(key=lambda case: case.acquisition_date)

        workspaces: list[CaseWorkspace] = []
        for case in selected_cases:
            workspace = getattr(case, "workspace", None)
            if workspace is None:
                continue
            if require_metrics and self._metrics_json_path(workspace) is None:
                continue
            workspaces.append(workspace)

        return DbResult.ok((normalized_start_date, normalized_end_date, workspaces))

    def _metrics_payload_for_case(self, case: MriCaseRecord) -> dict[str, Any]:
        workspace = getattr(case, "workspace", None)
        metrics_path = self._metrics_json_path(workspace)
        if metrics_path is None:
            raise FileNotFoundError("Metrics JSON does not exist for this case.")

        with metrics_path.open("r", encoding="utf-8") as f:
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
                if key not in {"mesh_paths"}
            },
        }

    def _date_entry(self, case: MriCaseRecord) -> dict[str, Any]:
        workspace = getattr(case, "workspace", None)
        metrics_ready = self._metrics_json_path(workspace) is not None
        mesh_ready = bool(workspace is not None and self._has_glb_outputs(workspace))
        pve_ready = bool(workspace is not None and getattr(workspace, "has_fast_pve_outputs", False))
        complete_visual = pve_ready

        return {
            "case_id": case.id,
            "acquisition_date": case.acquisition_date.isoformat(),
            "status": case.status,
            "ready_for_json": metrics_ready,
            "ready_for_visual": complete_visual,
            "has_metrics": metrics_ready,
            "has_meshes": mesh_ready,
            "has_pve_outputs": pve_ready,
        }

    def _metrics_json_path(self, workspace: CaseWorkspace | None) -> Any:
        if workspace is None:
            return None

        expected_path = workspace.metrics_json_path
        if expected_path.exists() and expected_path.is_file():
            return expected_path

        mesh_dir = getattr(workspace, "mesh_dir", None)
        if mesh_dir is None or not mesh_dir.exists() or not mesh_dir.is_dir():
            return None

        json_files = sorted(
            (path for path in mesh_dir.iterdir() if path.is_file() and path.name.lower().endswith(".json")),
            key=lambda path: ("metrics" not in path.name.lower(), path.name.lower()),
        )
        return json_files[0] if json_files else None

    def _has_glb_outputs(self, workspace: CaseWorkspace) -> bool:
        if any(path.exists() and path.is_file() for path in workspace.mesh_paths.values()):
            return True

        mesh_dir = getattr(workspace, "mesh_dir", None)
        if mesh_dir is None or not mesh_dir.exists() or not mesh_dir.is_dir():
            return False

        return any(path.is_file() and path.name.lower().endswith(".glb") for path in mesh_dir.iterdir())


__all__ = ["StatisticsService"]
