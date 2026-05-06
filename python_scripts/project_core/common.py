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


def discover_case(
    settings_obj: Settings,
    subject_filter: str | None = None,
) -> MRICase:
    """
    Discover exactly one raw MRI case from settings.input_mri_dir.

    input_mri is expected to contain raw NIfTI files directly, not per-subject
    folders. Because one subject must map to one raw input file, this function
    returns the matching case or raises an explicit error.
    """

    if subject_filter is None:
        raise ValueError(
            "A subject_id is required when scanning input_mri/. "
            "Use --subject <subject_id> or --input <path>."
        )

    found_case: MRICase | None = None

    for path in settings_obj.input_mri_dir.iterdir():
        if not path.is_file():
            continue

        if not is_nifti_path(path):
            continue

        case = MRICase.from_input_path(path)

        if case.subject_id != subject_filter:
            continue

        if found_case is not None:
            raise RuntimeError(
                "Duplicate raw MRI inputs found for subject "
                f"'{subject_filter}':\n"
                f"- {found_case.raw_path}\n"
                f"- {case.raw_path}\n\n"
                "input_mri/ must contain at most one NIfTI file per subject."
            )

        found_case = case

    if found_case is None:
        raise FileNotFoundError(
            f"No raw NIfTI input found for subject '{subject_filter}' in "
            f"{settings_obj.input_mri_dir}"
        )

    return found_case


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
        help="Required when scanning input_mri/. Process the matching subject_id.",
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
) -> MRICase:
    """
    Apply the shared input-selection policy:
    - --input means one explicit file
    - otherwise scan input_mri/, filtered by --subject
    """
    if args.input is not None:
        return build_single_case(args.input)

    return discover_case(settings_obj, subject_filter=args.subject)


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
        case = select_cases_from_args(args, settings_obj)

        if not case:
            print("No input MRI files found to process.")
            return 1
       
        print_case_header(case, title=case_header_title)
        result = process_case(case, settings_obj)

        if print_summary(result):
            return 0
        
        return 2

    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


__all__ = [
    "CaseRunResultLike",
    "is_nifti_path",
    "discover_case",
    "build_single_case",
    "build_prepared_case_paths",
    "parse_pipeline_args",
    "select_cases_from_args",
    "print_case_header",
    "default_preflight_checks",
    "run_pipeline_cli",
]
