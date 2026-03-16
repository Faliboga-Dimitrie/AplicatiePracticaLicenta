from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Settings, ensure_main_directories, settings
from .models import MRICase, build_case_paths
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


def _is_nifti_path(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def _discover_cases(settings: Settings, subject_filter: str | None = None) -> list[MRICase]:
    """
    Discover raw MRI inputs from input_mri/.
    Assumes input_mri contains raw inputs only.
    """
    if not settings.input_mri_dir.exists():
        raise FileNotFoundError(f"Input MRI directory does not exist: {settings.input_mri_dir}")

    files = sorted(
        p for p in settings.input_mri_dir.iterdir()
        if p.is_file() and _is_nifti_path(p)
    )

    cases = [MRICase.from_input_path(p) for p in files]

    if subject_filter is not None:
        cases = [c for c in cases if c.subject_id == subject_filter]

    return cases


def _build_single_case(input_path: Path) -> MRICase:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if not _is_nifti_path(input_path):
        raise ValueError(f"Input file is not a NIfTI (.nii or .nii.gz): {input_path}")

    return MRICase.from_input_path(input_path)


def _preflight_checks(settings: Settings) -> None:
    """
    Validate the minimum environment needed before processing starts.
    """
    ensure_main_directories(settings)

    if not settings.mni_template_path.exists():
        raise FileNotFoundError(
            f"MNI template not found: {settings.mni_template_path}\n"
            "Place the template in the configured mni_template folder."
        )

    if not settings.reorient_script.exists():
        raise FileNotFoundError(f"Reorientation script not found: {settings.reorient_script}")

    if not settings.fast_script.exists():
        raise FileNotFoundError(f"FAST script not found: {settings.fast_script}")


def _process_case(case: MRICase, settings: Settings) -> CaseRunResult:
    """
    Run the currently implemented preprocessing stages for one case:
      raw -> reoriented -> HD-BET -> FAST
    """
    paths = build_case_paths(case, settings)
    paths.ensure_stage_dirs()

    try:
        reoriented_path = run_reorientation(case, paths, settings)
        skull_stripped_path = run_skull_strip(case, paths, settings)
        segmentation_path = run_segmentation(case, paths, settings)

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


def _print_case_header(case: MRICase) -> None:
    print("=" * 80)
    print(f"Processing case: {case.subject_id}")
    print(f"Raw input: {case.raw_path}")
    print("=" * 80)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the T1 preprocessing pipeline: reorientation -> HD-BET -> FAST"
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Process a single NIfTI file instead of scanning input_mri/.",
    )

    parser.add_argument(
        "--subject",
        type=str,
        default=None,
        help="When scanning input_mri/, process only the matching subject_id.",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately when one case fails.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        _preflight_checks(settings)

        if args.input is not None:
            cases = [_build_single_case(args.input)]
        else:
            cases = _discover_cases(settings, subject_filter=args.subject)

        if not cases:
            print("No input MRI files found to process.")
            return 1

        results: list[CaseRunResult] = []

        for case in cases:
            _print_case_header(case)
            result = _process_case(case, settings)
            results.append(result)

            if result.success:
                print(f"[OK] Completed: {case.subject_id}")
            else:
                print(f"[FAIL] {case.subject_id}: {result.error}")
                if args.fail_fast:
                    _print_summary(results)
                    return 1

        _print_summary(results)

        return 0 if all(r.success for r in results) else 1

    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())