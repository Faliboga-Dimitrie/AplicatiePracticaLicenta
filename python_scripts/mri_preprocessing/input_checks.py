from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

import nibabel as nib
from nibabel.orientations import aff2axcodes

from ..project_core import MRICase


class OrientationStatus(Enum):
    ALREADY_STANDARD = auto()
    CAN_REORIENT = auto()
    NEEDS_REVIEW = auto()
    CANNOT_AUTO_REORIENT = auto()


@dataclass(frozen=True)
class InputCheckResult:
    subject_id: str
    input_path: Path
    status: OrientationStatus

    # header / geometry facts
    image_axcodes: tuple[str | None, str | None, str | None] | None
    template_axcodes: tuple[str | None, str | None, str | None] | None
    affine_source: str
    qform_code: int
    sform_code: int
    qform_axcodes: tuple[str | None, str | None, str | None] | None
    sform_axcodes: tuple[str | None, str | None, str | None] | None

    # loadability / shape
    loadable: bool
    ndim: int | None
    shape: tuple[int, ...] | None

    # decision support
    already_standard: bool
    has_usable_orientation_metadata: bool
    qform_sform_consistent: bool | None
    requires_manual_review: bool

    # explanation for logs / UI
    message: str

    @property
    def ok_for_pipeline(self) -> bool:
        return self.status in {
            OrientationStatus.ALREADY_STANDARD,
            OrientationStatus.CAN_REORIENT,
        }


def _safe_aff2axcodes(affine) -> tuple[str | None, str | None, str | None] | None:
    try:
        return tuple(aff2axcodes(affine))  # type: ignore[return-value]
    except Exception:
        return None


def _unloadable_result(
    *,
    subject_id: str,
    input_path: Path,
    message: str,
) -> InputCheckResult:
    return InputCheckResult(
        subject_id=subject_id,
        input_path=input_path,
        status=OrientationStatus.CANNOT_AUTO_REORIENT,
        image_axcodes=None,
        template_axcodes=None,
        affine_source="unknown",
        qform_code=0,
        sform_code=0,
        qform_axcodes=None,
        sform_axcodes=None,
        loadable=False,
        ndim=None,
        shape=None,
        already_standard=False,
        has_usable_orientation_metadata=False,
        qform_sform_consistent=None,
        requires_manual_review=True,
        message=message,
    )


def _determine_affine_source(img: nib.spatialimages.SpatialImage) -> str:
    hdr = img.header
    sform_code = int(hdr["sform_code"])
    qform_code = int(hdr["qform_code"])

    # NiBabel uses sform first, then qform, then fallback affine.
    if sform_code != 0:
        return "sform"
    if qform_code != 0:
        return "qform"
    return "fallback"


def _looks_like_structural_3d(shape: tuple[int, ...] | None, ndim: int | None) -> bool:
    if shape is None or ndim is None or ndim < 3:
        return False
    # We accept 3D and also 4D with singleton time/channel as a pragmatic check.
    return ndim == 3 or (ndim == 4 and shape[3] == 1)


def check_input_orientation(case: MRICase, settings: Any) -> InputCheckResult:
    """
    Decide whether an input MRI:
      - is already in the same voxel orientation as the chosen MNI template
      - can be safely passed to fslreorient2std
      - requires manual review / reconversion first
    """
    input_path = Path(case.raw_path)
    subject_id = str(case.subject_id)

    if not input_path.exists():
        return _unloadable_result(
            subject_id=subject_id,
            input_path=input_path,
            message=f"Input file does not exist: {input_path}",
        )

    try:
        img = nib.load(str(input_path))
    except Exception as exc:
        return _unloadable_result(
            subject_id=subject_id,
            input_path=input_path,
            message=f"Failed to load NIfTI with nibabel: {exc}",
        )

    mni_template_path = getattr(settings, "mni_template_path", None)
    if mni_template_path is None:
        raise AttributeError("settings must expose mni_template_path for input_checks.py")

    mni = nib.load(str(mni_template_path))

    hdr = img.header
    qform_code = int(hdr["qform_code"])
    sform_code = int(hdr["sform_code"])

    shape = tuple(int(x) for x in img.shape)
    ndim = img.ndim

    affine_source = _determine_affine_source(img)
    image_axcodes = _safe_aff2axcodes(img.affine)
    template_axcodes = _safe_aff2axcodes(mni.affine)

    qform, _ = img.get_qform(coded=True)
    sform, _ = img.get_sform(coded=True)

    qform_axcodes = _safe_aff2axcodes(qform) if qform_code != 0 and qform is not None else None
    sform_axcodes = _safe_aff2axcodes(sform) if sform_code != 0 and sform is not None else None

    has_usable_orientation_metadata = (
        image_axcodes is not None
        and all(axis is not None for axis in image_axcodes)
        and (qform_code != 0 or sform_code != 0)
    )
    qform_sform_consistent = (
        qform_axcodes == sform_axcodes
        if qform_code != 0 and sform_code != 0
        else None
    )
    already_standard = (
        image_axcodes is not None
        and template_axcodes is not None
        and image_axcodes == template_axcodes
    )

    def loaded_result(
        *,
        status: OrientationStatus,
        message: str,
        already_standard_value: bool = already_standard,
        usable_metadata: bool = has_usable_orientation_metadata,
        forms_consistent: bool | None = qform_sform_consistent,
        requires_review: bool,
    ) -> InputCheckResult:
        return InputCheckResult(
            subject_id=subject_id,
            input_path=input_path,
            status=status,
            image_axcodes=image_axcodes,
            template_axcodes=template_axcodes,
            affine_source=affine_source,
            qform_code=qform_code,
            sform_code=sform_code,
            qform_axcodes=qform_axcodes,
            sform_axcodes=sform_axcodes,
            loadable=True,
            ndim=ndim,
            shape=shape,
            already_standard=already_standard_value,
            has_usable_orientation_metadata=usable_metadata,
            qform_sform_consistent=forms_consistent,
            requires_manual_review=requires_review,
            message=message,
        )

    if not _looks_like_structural_3d(shape, ndim):
        return loaded_result(
            status=OrientationStatus.NEEDS_REVIEW,
            requires_review=True,
            message="Image loaded, but shape/dimensionality does not look like a standard structural 3D T1.",
        )

    if image_axcodes is None or template_axcodes is None:
        return loaded_result(
            status=OrientationStatus.NEEDS_REVIEW,
            already_standard_value=False,
            usable_metadata=False,
            requires_review=True,
            message="Could not derive axis codes from the image affine and/or the MNI template affine.",
        )

    if qform_code == 0 and sform_code == 0:
        return loaded_result(
            status=OrientationStatus.NEEDS_REVIEW,
            usable_metadata=False,
            requires_review=True,
            message=(
                "Both qform_code and sform_code are 0, so orientation metadata is not trustworthy enough "
                "for automatic reorientation."
            ),
        )

    if qform_sform_consistent is False:
        return loaded_result(
            status=OrientationStatus.NEEDS_REVIEW,
            usable_metadata=False,
            forms_consistent=False,
            requires_review=True,
            message="qform and sform imply different voxel-axis orientations; manual review or reconversion is needed.",
        )

    if already_standard:
        return loaded_result(
            status=OrientationStatus.ALREADY_STANDARD,
            already_standard_value=True,
            requires_review=False,
            message="Image axis codes already match the chosen MNI template orientation.",
        )

    if has_usable_orientation_metadata:
        return loaded_result(
            status=OrientationStatus.CAN_REORIENT,
            already_standard_value=False,
            usable_metadata=True,
            requires_review=False,
            message="Image can be passed to fslreorient2std.",
        )

    return loaded_result(
        status=OrientationStatus.NEEDS_REVIEW,
        already_standard_value=False,
        usable_metadata=False,
        requires_review=True,
        message="Orientation metadata is not strong enough for automatic reorientation.",
    )
