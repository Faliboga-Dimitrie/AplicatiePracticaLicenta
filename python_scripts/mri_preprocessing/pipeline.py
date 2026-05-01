from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..project_core.common import run_pipeline_cli
from ..project_core.config import Settings, ensure_main_directories, settings
from ..project_core.domain import MRICase
from ..project_core.ports import (
    ReorientationBackend,
    ReorientationResult,
    SegmentationBackend,
    SegmentationResult,
    SkullStripBackend,
    SkullStripResult,
    WorkspaceProvider,
)
from ..project_core.workspace import CaseWorkspace, FileSystemWorkspaceProvider
from .reorient import FslReorientationBackend
from .segmentation import FslFastSegmentationBackend
from .skull_strip import HdBetSkullStripBackend


@dataclass(frozen=True)
class PreprocessingResult:
    """
    Successful preprocessing result for one case.

    This object is intentionally independent from CLI printing. A future API can
    serialize it, while CLI can still display it in a human-readable format.
    """

    subject_id: str
    workspace: CaseWorkspace
    reorientation: ReorientationResult
    skull_strip: SkullStripResult
    segmentation: SegmentationResult

    @property
    def reoriented_path(self) -> Path:
        return self.reorientation.output_path

    @property
    def skull_stripped_path(self) -> Path:
        return self.skull_strip.image_path

    @property
    def segmentation_path(self) -> Path | None:
        return self.segmentation.seg_path

    @property
    def pve_paths(self) -> dict[str, Path]:
        return dict(self.segmentation.pve_paths)


@dataclass(frozen=True)
class CaseRunResult:
    """
    CLI-friendly wrapper around a preprocessing run.

    run_pipeline_cli only requires subject_id/success/error, but keeping the full
    PreprocessingResult makes summaries and future callers more useful.
    """

    subject_id: str
    success: bool
    result: PreprocessingResult | None = None
    error: str | None = None

    @property
    def reoriented_path(self) -> Path | None:
        return self.result.reoriented_path if self.result is not None else None

    @property
    def skull_stripped_path(self) -> Path | None:
        return self.result.skull_stripped_path if self.result is not None else None

    @property
    def segmentation_path(self) -> Path | None:
        return self.result.segmentation_path if self.result is not None else None


class PreprocessingPipeline:
    """
    Orchestrates raw MRI preprocessing through injected ports.

    The pipeline is closed for modification with respect to concrete tools: it
    does not know whether reorientation comes from FSL, skull stripping from
    HD-BET, or segmentation from FAST. Those are replaceable implementations of
    the backend protocols.
    """

    def __init__(
        self,
        *,
        workspace_provider: WorkspaceProvider,
        reorientation_backend: ReorientationBackend,
        skull_strip_backend: SkullStripBackend,
        segmentation_backend: SegmentationBackend,
    ):
        self.workspace_provider = workspace_provider
        self.reorientation_backend = reorientation_backend
        self.skull_strip_backend = skull_strip_backend
        self.segmentation_backend = segmentation_backend

    def run_case(self, case: MRICase) -> PreprocessingResult:
        workspace = self.workspace_provider.create_workspace(case)

        reorientation = self.reorientation_backend.run(case, workspace)
        skull_strip = self.skull_strip_backend.run(
            reorientation.output_path,
            workspace,
        )
        segmentation = self.segmentation_backend.run(
            skull_strip.image_path,
            workspace,
        )

        return PreprocessingResult(
            subject_id=case.subject_id,
            workspace=workspace,
            reorientation=reorientation,
            skull_strip=skull_strip,
            segmentation=segmentation,
        )


def build_default_preprocessing_pipeline(
    settings_obj: Settings = settings,
) -> PreprocessingPipeline:
    """
    Build the default production preprocessing pipeline.

    This is the only place that wires the concrete FSL/HD-BET/FAST adapters
    together. Tests, API code, or future variants can inject different backends.
    """
    return PreprocessingPipeline(
        workspace_provider=FileSystemWorkspaceProvider(settings_obj),
        reorientation_backend=FslReorientationBackend(settings_obj),
        skull_strip_backend=HdBetSkullStripBackend(settings_obj),
        segmentation_backend=FslFastSegmentationBackend(settings_obj),
    )


# -----------------------------------------------------------------------------
# CLI integration
# -----------------------------------------------------------------------------

def _preflight_checks(settings_obj: Settings) -> None:
    """
    Validate the minimum environment needed before preprocessing starts.
    """
    ensure_main_directories(settings_obj)

    if not settings_obj.mni_template_path.exists():
        raise FileNotFoundError(
            f"MNI template not found: {settings_obj.mni_template_path}\n"
            "Place the template in the configured mni_template folder."
        )

    if not settings_obj.reorient_script.exists():
        raise FileNotFoundError(
            f"Reorientation script not found: {settings_obj.reorient_script}"
        )

    if not settings_obj.fast_script.exists():
        raise FileNotFoundError(f"FAST script not found: {settings_obj.fast_script}")


def _process_case(case: MRICase, settings_obj: Settings) -> CaseRunResult:
    pipeline = build_default_preprocessing_pipeline(settings_obj)

    try:
        result = pipeline.run_case(case)
        return CaseRunResult(
            subject_id=case.subject_id,
            success=True,
            result=result,
        )

    except Exception as exc:
        return CaseRunResult(
            subject_id=case.subject_id,
            success=False,
            error=str(exc),
        )


def _print_summary(results: list[CaseRunResult]) -> None:
    print("\n" + "#" * 80)
    print("PREPROCESSING SUMMARY")
    print("#" * 80)

    ok_count = 0
    fail_count = 0

    for res in results:
        if res.success and res.result is not None:
            ok_count += 1
            print(f"[OK] {res.subject_id}")
            print(f"     reoriented    : {res.reoriented_path}")
            print(f"     skull-stripped: {res.skull_stripped_path}")
            print(f"     segmentation  : {res.segmentation_path}")
        else:
            fail_count += 1
            print(f"[FAIL] {res.subject_id}")
            print(f"       error: {res.error}")

    print("-" * 80)
    print(f"Successful: {ok_count}")
    print(f"Failed    : {fail_count}")
    print(f"Total     : {len(results)}")


def main() -> int:
    return run_pipeline_cli(
        description="Run the T1 preprocessing pipeline: reorientation -> HD-BET -> FAST",
        settings_obj=settings,
        preflight_checks=_preflight_checks,
        process_case=_process_case,
        print_summary=_print_summary,
        case_header_title="Processing case",
        success_message=lambda case, _result: f"[OK] Completed preprocessing: {case.subject_id}",
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PreprocessingResult",
    "CaseRunResult",
    "PreprocessingPipeline",
    "build_default_preprocessing_pipeline",
    "main",
]
