from __future__ import annotations


def safe_nifti_upload_filename(filename: str | None, *, default: str) -> str:
    """
    Return a path-safe uploaded NIfTI filename.

    Browser-provided filenames are untrusted. This helper keeps only a flat file
    name by replacing path separators, applies a default when the name is empty,
    and accepts only .nii / .nii.gz NIfTI files.
    """
    candidate = filename or default
    name = candidate.replace("\\", "_").replace("/", "_").strip() or default

    lower = name.lower()
    if not (lower.endswith(".nii") or lower.endswith(".nii.gz")):
        raise ValueError("Upload must be a .nii or .nii.gz NIfTI file.")

    return name


__all__ = ["safe_nifti_upload_filename"]
