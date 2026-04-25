from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..project_core import Settings, ensure_main_directories, settings
from ..project_core import MRICase
from ..project_core import build_prepared_case_paths, run_pipeline_cli
from .reorient import run_reorientation
from .segmentation import run_segmentation
from .skull_strip import run_skull_strip


@dataclass
class CaseRunResult:
    subject_id: str
    success: bool
    reoriented_path: Path | None = None
    skull_stripped_path: Path | None = None
    segmentation_path: Path | None = None
    error: str | None = None


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
    """
    Run the currently implemented preprocessing stages for one case:
      raw -> reoriented -> HD-BET -> FAST
    """
    paths = build_prepared_case_paths(case, settings_obj)

    try:
        reoriented_path = run_reorientation(case, paths, settings_obj)
        skull_stripped_path = run_skull_strip(case, paths, settings_obj)
        segmentation_path = run_segmentation(case, paths, settings_obj)

        return CaseRunResult(
            subject_id=case.subject_id,
            success=True,
            reoriented_path=reoriented_path,
            skull_stripped_path=skull_stripped_path,
            segmentation_path=segmentation_path,
        )

    except Exception as exc:
        return CaseRunResult(
            subject_id=case.subject_id,
            success=False,
            error=str(exc),
        )


def _print_summary(results: list[CaseRunResult]) -> None:
    print("\n" + "#" * 80)
    print("PIPELINE SUMMARY")
    print("#" * 80)

    ok_count = 0
    fail_count = 0

    for res in results:
        if res.success:
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
        success_message=lambda case, _result: f"[OK] Completed: {case.subject_id}",
    )


if __name__ == "__main__":
    raise SystemExit(main())