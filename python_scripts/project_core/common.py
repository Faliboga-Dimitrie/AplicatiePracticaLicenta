from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Protocol, TypeVar

from .config import Settings, ensure_main_directories, settings
from .domain import MRICase
from .workspace import CaseWorkspace, build_case_workspace


class CaseSelectionError(RuntimeError):
    """
    Raised when the CLI arguments do not identify exactly one MRI acquisition.
    """


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

def _first_nifti_file_for_acquisition_dir(acquisition_dir: Path) -> Path | None:
    """
    Return the first NIfTI file found inside one acquisition/date folder.

    Checks:
        input_mri/<subject>/<date>/<file>.nii.gz

    Then checks:
        input_mri/<subject>/<date>/mri/<file>.nii.gz
    """
    for path in acquisition_dir.iterdir():
        if path.is_file() and is_nifti_path(path):
            return path

    mri_dir = acquisition_dir / "mri"
    if not mri_dir.is_dir():
        return None

    for path in mri_dir.iterdir():
        if path.is_file() and is_nifti_path(path):
            return path

    return None

def discover_case(
    settings_obj: Settings,
    subject_filter: str | None = None,
    acquisition_date_filter: str | None = None,
) -> MRICase | None:
    """
    Greedily discover the first MRI matching the optional filters.

    Expected layout:
        input_mri/<subject_id>/<YYYY-MM-DD>/<file>.nii.gz

    Also accepts:
        input_mri/<subject_id>/<YYYY-MM-DD>/mri/<file>.nii.gz

    This intentionally does not sort or collect all matches.
    The first matching file returned by the filesystem is selected.
    """
    root = Path(settings_obj.input_mri_dir)
    if not root.exists():
        return None

    for subject_dir in root.iterdir():
        if not subject_dir.is_dir():
            continue

        subject_id = subject_dir.name

        if subject_filter is not None and subject_id != subject_filter:
            continue

        for acquisition_dir in subject_dir.iterdir():
            if not acquisition_dir.is_dir():
                continue

            acquisition_date = acquisition_dir.name

            if (
                acquisition_date_filter is not None
                and acquisition_date != acquisition_date_filter
            ):
                continue

            nifti_path = _first_nifti_file_for_acquisition_dir(acquisition_dir)
            if nifti_path is None:
                continue

            return MRICase.from_input_path(
                nifti_path,
                subject_id=subject_id,
                acquisition_date=acquisition_date,
            )

    return None

def build_single_case(
    input_path: Path,
    *,
    subject_id: str | None = None,
    acquisition_date: str | None = None,
) -> MRICase:
    """Validate one explicit input path and convert it to an MRICase."""
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    if not is_nifti_path(input_path):
        raise ValueError(f"Input file is not a NIfTI (.nii or .nii.gz): {input_path}")

    return MRICase.from_input_path(
        input_path,
        subject_id=subject_id,
        acquisition_date=acquisition_date,
    )


def build_prepared_case_paths(case: MRICase, settings_obj: Settings) -> CaseWorkspace:
    """
    Build a filesystem workspace and create the subject/date stage directories.

    Kept under the old function name for compatibility with existing pipeline
    modules while the codebase migrates from CasePaths to CaseWorkspace.
    """
    workspace = build_case_workspace(case, settings_obj)
    workspace.ensure_directories()
    workspace.ensure_input_file(overwrite=settings_obj.overwrite)
    return workspace


def parse_pipeline_args(description: str) -> argparse.Namespace:
    """Shared CLI arguments used by pipeline entry points."""
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Process one explicit NIfTI file. If the path is outside the "
            "standardized input tree, also pass --subject and --date."
        ),
    )

    parser.add_argument(
        "--subject",
        type=str,
        default=None,
        help="Process the matching subject_id.",
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Process the matching acquisition date/session, in YYYY-MM-DD format.",
    )

    return parser.parse_args()


def _format_case_matches(cases: list[MRICase], *, limit: int = 10) -> str:
    """Human-readable case list for ambiguous CLI selections."""
    shown = cases[:limit]
    lines = [f"  - {case.case_id}: {case.raw_path}" for case in shown]

    remaining = len(cases) - len(shown)
    if remaining > 0:
        lines.append(f"  ... and {remaining} more")

    return "\n".join(lines)


def select_case_from_args(
    args: argparse.Namespace,
    settings_obj: Settings,
) -> MRICase:
    """
    Apply the shared input-selection policy and return one MRICase.

    Selection rules:
    - --input always means that exact file;
    - without --input, scan the standardized input tree;
    - return the first MRI matching --subject and/or --date;
    - no sorting, no full list building, no ambiguity check.
    """
    if args.input is not None:
        return build_single_case(
            args.input,
            subject_id=args.subject,
            acquisition_date=args.date,
        )

    case = discover_case(
        settings_obj,
        subject_filter=args.subject,
        acquisition_date_filter=args.date,
    )

    if case is None:
        raise CaseSelectionError("Raised when the CLI arguments do not match any MRI acquisition.")

    return case

def print_case_header(case: MRICase, title: str = "Processing case") -> None:
    """Standard visual header for one case run."""
    print("=" * 80)
    print(f"{title}: {case.case_id}")
    print(f"Subject: {case.subject_id}")
    print(f"Date   : {case.acquisition_date}")
    print(f"Raw input: {case.raw_path}")
    print("=" * 80)


def default_preflight_checks(settings_obj: Settings) -> None:
    """Minimal shared preflight."""
    ensure_main_directories(settings_obj)


def run_pipeline_cli(
    *,
    description: str,
    process_case: Callable[[MRICase, Settings], R],
    print_summary: Callable[[R], bool],
    settings_obj: Settings = settings,
    preflight_checks: Callable[[Settings], None] = default_preflight_checks,
    case_header_title: str = "Processing case",
) -> int:
    """
    Shared CLI orchestration for single-case pipeline entry points.

    Stage-specific modules provide:
    - how to process one case;
    - how to print the result summary;
    - any extra preflight checks.

    Return codes:
    - 0: selected case processed successfully;
    - 1: no case or ambiguous case selection;
    - 2: selected case ran but the pipeline reported failure;
    - 3: fatal setup/unhandled error.
    """
    args = parse_pipeline_args(description)

    try:
        preflight_checks(settings_obj)
        case = select_case_from_args(args, settings_obj)

        print_case_header(case, title=case_header_title)
        result = process_case(case, settings_obj)

        ok = print_summary(result)
        return 0 if ok else 2

    except CaseSelectionError as exc:
        print(str(exc))
        return 1

    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 3


__all__ = [
    "CaseSelectionError",
    "CaseRunResultLike",
    "is_nifti_path",
    "discover_cases",
    "build_single_case",
    "build_prepared_case_paths",
    "parse_pipeline_args",
    "select_case_from_args",
    "print_case_header",
    "default_preflight_checks",
    "run_pipeline_cli",
]
