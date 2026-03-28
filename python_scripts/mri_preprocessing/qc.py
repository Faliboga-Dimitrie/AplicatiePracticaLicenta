from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from matplotlib.colors import ListedColormap
from nibabel.processing import resample_from_to
from typing import Optional

from ..project_core import Settings

from ..project_core import MRICase, CasePaths


def _load_canonical_data(path: Path, like: nib.Nifti1Image | None = None, order: int = 1) -> tuple[nib.Nifti1Image, np.ndarray]:
    """
    Load a NIfTI image, optionally resample to a reference image grid, then
    convert to closest canonical orientation (RAS+) for consistent plotting.

    order=0 for labels, order=1 for continuous-valued images.
    """
    img = nib.load(str(path))
    if like is not None:
        img = resample_from_to(img, like, order=order)
    img = nib.as_closest_canonical(img)
    data = np.asarray(img.get_fdata())
    return img, data


def _robust_normalize(arr: np.ndarray) -> np.ndarray:
    """
    Normalize MRI intensities for display using robust percentiles.
    """
    arr = np.asarray(arr, dtype=np.float32)

    finite = np.isfinite(arr)
    if not np.any(finite):
        return np.zeros_like(arr, dtype=np.float32)

    vals = arr[finite]
    lo = np.percentile(vals, 1)
    hi = np.percentile(vals, 99)

    if hi <= lo:
        hi = vals.max()
        lo = vals.min()

    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)

    out = (arr - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def _axial_slice_for_display(arr3d: np.ndarray, k: int) -> np.ndarray:
    """
    Return an axial slice formatted for display.
    For canonical RAS+ data, transpose to x-horizontal / y-vertical and flip
    vertically so the image looks natural in matplotlib.
    """
    sl = arr3d[:, :, k]
    return np.flipud(sl.T)


def _pick_center_slice(arr3d: np.ndarray) -> int:
    return arr3d.shape[2] // 2


def _pick_nonzero_center_slice(arr3d: np.ndarray) -> int:
    """
    Choose a slice near the center of the nonzero content along z.
    Useful for skull-stripped images and masks.
    """
    nz = np.where(np.any(arr3d != 0, axis=(0, 1)))[0]
    if len(nz) == 0:
        return _pick_center_slice(arr3d)
    return int(nz[len(nz) // 2])


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_reorientation_qc(case: MRICase, paths: CasePaths) -> Path:
    """
    Save side-by-side QC for raw vs reoriented MRI.
    """
    raw_img, raw = _load_canonical_data(paths.raw_path)
    _, reo = _load_canonical_data(paths.reoriented_path)

    k_raw = _pick_center_slice(raw)
    k_reo = _pick_center_slice(reo)

    raw_disp = _axial_slice_for_display(_robust_normalize(raw), k_raw)
    reo_disp = _axial_slice_for_display(_robust_normalize(reo), k_reo)

    out_path = paths.qc_reorientation_png
    _ensure_parent(out_path)

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].imshow(raw_disp, cmap="gray")
    axes[0].set_title("Raw input")
    axes[0].axis("off")

    axes[1].imshow(reo_disp, cmap="gray")
    axes[1].set_title("Reoriented")
    axes[1].axis("off")

    fig.suptitle(f"{case.subject_id} — Reorientation QC")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return out_path


def save_bet_qc(case: MRICase, paths: CasePaths) -> Path:
    """
    Save QC for skull stripping:
    - reoriented T1 with HD-BET mask overlay
    - skull-stripped result
    """
    base_img, base = _load_canonical_data(paths.reoriented_path)
    _, mask = _load_canonical_data(paths.skull_stripped_mask_path, like=base_img, order=0)
    _, bet = _load_canonical_data(paths.skull_stripped_path, like=base_img, order=1)

    k = _pick_nonzero_center_slice(mask)

    base_n = _robust_normalize(base)
    bet_n = _robust_normalize(bet)

    base_disp = _axial_slice_for_display(base_n, k)
    bet_disp = _axial_slice_for_display(bet_n, k)
    mask_disp = _axial_slice_for_display((mask > 0).astype(np.uint8), k)

    out_path = paths.qc_bet_png
    _ensure_parent(out_path)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].imshow(base_disp, cmap="gray")
    axes[0].imshow(mask_disp, cmap="autumn", alpha=0.35)
    axes[0].set_title("Reoriented T1 + BET mask")
    axes[0].axis("off")

    axes[1].imshow(bet_disp, cmap="gray")
    axes[1].set_title("Skull-stripped output")
    axes[1].axis("off")

    fig.suptitle(f"{case.subject_id} — HD-BET QC")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return out_path


def save_fast_qc(case: MRICase, paths: CasePaths) -> Path:
    """
    Save FAST QC:
    - skull-stripped T1
    - skull-stripped T1 + segmentation overlay

    FAST labels:
      0 = background
      1 = CSF
      2 = GM
      3 = WM
    """
    base_img, base = _load_canonical_data(paths.fast_input_path)
    _, seg = _load_canonical_data(paths.fast_seg_path, like=base_img, order=0)

    k = _pick_nonzero_center_slice(seg)

    base_disp = _axial_slice_for_display(_robust_normalize(base), k)
    seg_disp = _axial_slice_for_display(seg, k)

    # Transparent background for label 0
    cmap = ListedColormap([
        (0, 0, 0, 0.0),   # background transparent
        (1.0, 0.2, 0.2, 0.45),  # CSF
        (0.2, 1.0, 0.2, 0.45),  # GM
        (0.2, 0.4, 1.0, 0.45),  # WM
    ])

    out_path = paths.qc_fast_png
    _ensure_parent(out_path)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].imshow(base_disp, cmap="gray")
    axes[0].set_title("FAST input (skull-stripped T1)")
    axes[0].axis("off")

    axes[1].imshow(base_disp, cmap="gray")
    axes[1].imshow(seg_disp, cmap=cmap, interpolation="nearest", vmin=0, vmax=3)
    axes[1].set_title("FAST segmentation overlay")
    axes[1].axis("off")

    fig.suptitle(f"{case.subject_id} — FAST QC")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return out_path


def run_available_qc(case: MRICase, paths: CasePaths) -> dict[str, Path]:
    """
    Run all QC steps for which the required files exist.
    Returns a dictionary of generated QC outputs.
    """
    outputs: dict[str, Path] = {}

    if paths.raw_path.exists() and paths.reoriented_path.exists():
        outputs["reorientation"] = save_reorientation_qc(case, paths)

    if (
        paths.reoriented_path.exists()
        and paths.skull_stripped_path.exists()
        and paths.skull_stripped_mask_path.exists()
    ):
        outputs["hd_bet"] = save_bet_qc(case, paths)

    if paths.fast_input_path.exists() and paths.fast_seg_path.exists():
        outputs["fast"] = save_fast_qc(case, paths)

    return outputs

def _handle_qc_result(
    qc_name: str,
    output_path: Optional[Path],
    settings: Settings,
    exc: Exception | None = None,
) -> Optional[Path]:
    if exc is None:
        return output_path

    if settings.fail_on_qc_error:
        raise RuntimeError(f"{qc_name} QC failed: {exc}") from exc

    print(f"[QC warning] {qc_name} QC failed: {exc}")
    return None


def maybe_save_reorientation_qc(
    case: MRICase,
    paths: CasePaths,
    settings: Settings,
) -> Optional[Path]:
    if not settings.generate_qc:
        return None

    try:
        return save_reorientation_qc(case, paths)
    except Exception as exc:
        return _handle_qc_result("Reorientation", None, settings, exc)


def maybe_save_bet_qc(
    case: MRICase,
    paths: CasePaths,
    settings: Settings,
) -> Optional[Path]:
    if not settings.generate_qc:
        return None

    try:
        return save_bet_qc(case, paths)
    except Exception as exc:
        return _handle_qc_result("HD-BET", None, settings, exc)


def maybe_save_fast_qc(
    case: MRICase,
    paths: CasePaths,
    settings: Settings,
) -> Optional[Path]:
    if not settings.generate_qc:
        return None

    try:
        return save_fast_qc(case, paths)
    except Exception as exc:
        return _handle_qc_result("FAST", None, settings, exc)