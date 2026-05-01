from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from .config import Settings, ensure_main_directories, settings
from .domain import MRICase
from .workspace import CaseWorkspace, build_case_workspace


class CaseRunResultLike(Protocol):
    """
    Minimal shape expected by the shared CLI runner.

    Concrete pipeline modules can keep richer result dataclasses as long as
    they expose these fields.
    """

    subject_id: str
    success: bool
    error: str | None


R = TypeVar("R", bound=CaseRunResultLike)


def is_nifti_path(path: Path) -> bool:
    """Return True for .nii and .nii.gz files."""
    name = path.name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def discover_cases(
    settings_obj: Settings,
    subject_filter: str | None = None,
) -> list[MRICase]:
    """
    Discover raw MRI inputs from settings.input_mri_dir.
    Assumes input_mri contains raw NIfTI inputs only.
    """
    if not settings_obj.input_mri_dir.exists():
        raise FileNotFoundError(
            f"Input MRI directory does not exist: {settings_obj.input_mri_dir}"
        )

    files = sorted(
        path
        for path in settings_obj.input_mri_dir.iterdir()
        if path.is_file() and is_nifti_path(path)
    )

    cases = [MRICase.from_input_path(path) for path in files]

    if subject_filter is not None:
        cases = [case for case in cases if case.subject_id == subject_filter]

    return cases


def build_single_case(input_path: Path) -> MRICase:
    """Validate one explicit input path and convert it to an MRICase."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if not is_nifti_path(input_path):
        raise ValueError(f"Input file is not a NIfTI (.nii or .nii.gz): {input_path}")

    return MRICase.from_input_path(input_path)


def build_prepared_case_paths(case: MRICase, settings_obj: Settings) -> CaseWorkspace:
    """
    Build a filesystem workspace and create the per-subject stage directories.

    Kept under the old function name for compatibility with existing pipeline
    modules while the codebase migrates from CasePaths to CaseWorkspace.
    """
    workspace = build_case_workspace(case, settings_obj)
    workspace.ensure_directories()
    return workspace


def parse_pipeline_args(description: str) -> argparse.Namespace:
    """Shared CLI arguments used by pipeline entry points."""
    parser = argparse.ArgumentParser(description=description)

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


def select_cases_from_args(
    args: argparse.Namespace,
    settings_obj: Settings,
) -> list[MRICase]:
    """
    Apply the shared input-selection policy:
    - --input means one explicit file
    - otherwise scan input_mri/, optionally filtered by --subject
    """
    if args.input is not None:
        return [build_single_case(args.input)]

    return discover_cases(settings_obj, subject_filter=args.subject)


def print_case_header(case: MRICase, title: str = "Processing case") -> None:
    """Standard visual header for one case run."""
    print("=" * 80)
    print(f"{title}: {case.subject_id}")
    print(f"Raw input: {case.raw_path}")
    print("=" * 80)


def default_preflight_checks(settings_obj: Settings) -> None:
    """Minimal shared preflight."""
    ensure_main_directories(settings_obj)


def run_pipeline_cli(
    *,
    description: str,
    process_case: Callable[[MRICase, Settings], R],
    print_summary: Callable[[list[R]], None],
    settings_obj: Settings = settings,
    preflight_checks: Callable[[Settings], None] = default_preflight_checks,
    case_header_title: str = "Processing case",
    success_message: Callable[[MRICase, R], str] | None = None,
) -> int:
    """
    Shared CLI orchestration for pipeline entry points.

    Stage-specific modules provide:
    - how to process one case
    - how to print their result summary
    - any extra preflight checks
    - the success message text
    """
    args = parse_pipeline_args(description)

    try:
        preflight_checks(settings_obj)
        cases = select_cases_from_args(args, settings_obj)

        if not cases:
            print("No input MRI files found to process.")
            return 1

        results: list[R] = []

        for case in cases:
            print_case_header(case, title=case_header_title)
            result = process_case(case, settings_obj)
            results.append(result)

            if result.success:
                if success_message is None:
                    print(f"[OK] Completed: {case.subject_id}")
                else:
                    print(success_message(case, result))
            else:
                print(f"[FAIL] {case.subject_id}: {result.error}")
                if args.fail_fast:
                    print_summary(results)
                    return 1

        print_summary(results)
        return 0 if all(result.success for result in results) else 1

    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


__all__ = [
    "CaseRunResultLike",
    "is_nifti_path",
    "discover_cases",
    "build_single_case",
    "build_prepared_case_paths",
    "parse_pipeline_args",
    "select_cases_from_args",
    "print_case_header",
    "default_preflight_checks",
    "run_pipeline_cli",
]
