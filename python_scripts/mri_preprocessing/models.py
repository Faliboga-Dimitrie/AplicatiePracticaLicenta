from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from python_scripts.project_core.ports import ReorientationResult, SegmentationResult, SkullStripResult
from python_scripts.project_core.workspace import CaseWorkspace


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
    
all__ = [
    "PreprocessingResult",
    "CaseRunResult",
]