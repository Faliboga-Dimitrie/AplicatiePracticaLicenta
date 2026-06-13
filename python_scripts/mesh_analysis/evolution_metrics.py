from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Mapping, Sequence

from ..project_core.domain import TissueSurfaces, TissueVolumes
from .evolution_models import EvolutionCaseMetrics, EvolutionMriArtifacts, JsonDict, _normalize_tissues


def _validate_metric_inputs(selected: Sequence[EvolutionMriArtifacts]) -> None:
    missing: list[Path] = []
    for mri in selected:
        missing.extend(mri.missing_metric_paths())

    if missing:
        missing_str = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Cannot build MRI evolution JSON. Missing metrics files:\n{missing_str}")


def _load_metrics(mri: EvolutionMriArtifacts) -> EvolutionCaseMetrics:
    with mri.metrics_json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    volumes = TissueVolumes.from_mapping(_require_mapping(payload, "volumes")).as_tissue_dict()
    surfaces = TissueSurfaces.from_mapping(_require_mapping(payload, "surfaces")).as_tissue_dict()

    return EvolutionCaseMetrics(
        subject_id=mri.subject_id,
        acquisition_date=mri.acquisition_date,
        volumes=volumes,
        surfaces=surfaces,
    )


def _build_metric_point(
    *,
    current: EvolutionCaseMetrics,
    baseline: EvolutionCaseMetrics,
    previous: EvolutionCaseMetrics | None,
    index: int,
) -> JsonDict:
    return {
        "index": index,
        "acquisition_date": current.acquisition_date,
        "is_baseline": current.acquisition_date == baseline.acquisition_date,
        "compared_to_baseline_date": baseline.acquisition_date,
        "compared_to_previous_date": previous.acquisition_date if previous is not None else None,
        "volumes_mm3": _compare_metric_group(
            current=current.volumes,
            baseline=baseline.volumes,
            previous=previous.volumes if previous is not None else None,
        ),
        "surfaces_mm2": _compare_metric_group(
            current=current.surfaces,
            baseline=baseline.surfaces,
            previous=previous.surfaces if previous is not None else None,
        ),
    }


def _compare_metric_group(
    *,
    current: Mapping[str, float],
    baseline: Mapping[str, float],
    previous: Mapping[str, float] | None,
) -> JsonDict:
    compared: JsonDict = {}

    for tissue in _normalize_tissues(None):
        value = float(current[tissue])
        baseline_value = float(baseline[tissue])
        previous_value = float(previous[tissue]) if previous is not None else None

        compared[tissue] = {
            "value": value,
            "baseline_value": baseline_value,
            "absolute_change_from_baseline": value - baseline_value,
            "ratio_to_baseline_percent": _safe_ratio_percent(value, baseline_value),
            "change_from_baseline_percent": _safe_change_percent(value, baseline_value),
            "previous_value": previous_value,
            "absolute_change_from_previous": None if previous_value is None else value - previous_value,
            "ratio_to_previous_percent": None if previous_value is None else _safe_ratio_percent(value, previous_value),
            "change_from_previous_percent": None if previous_value is None else _safe_change_percent(value, previous_value),
        }

    return compared


def _build_statistics(points: Sequence[JsonDict]) -> JsonDict:
    stats: JsonDict = {}

    for metric_group in ("volumes_mm3", "surfaces_mm2"):
        group_stats: JsonDict = {}

        for tissue in _normalize_tissues(None):
            values: list[float] = []
            baseline_changes: list[float] = []
            previous_changes: list[float] = []

            for point in points:
                tissue_payload = _nested_mapping(point, metric_group, tissue)
                values.append(_require_float(tissue_payload.get("value"), label=f"{metric_group}.{tissue}.value"))
                _append_optional_float(baseline_changes, tissue_payload.get("change_from_baseline_percent"))
                _append_optional_float(previous_changes, tissue_payload.get("change_from_previous_percent"))

            # The first baseline change is always 0.0. Excluding it makes the
            # reported average describe actual follow-up change, not baseline identity.
            baseline_changes_without_first = baseline_changes[1:] if len(baseline_changes) > 1 else []

            group_stats[tissue] = {
                "values": _basic_stats(values),
                "change_from_baseline_percent": _basic_stats(baseline_changes_without_first),
                "change_from_previous_percent": _basic_stats(previous_changes),
            }

        stats[metric_group] = group_stats

    return stats


def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, float]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Metrics JSON is missing an object field named '{key}'.")
    return value  # type: ignore[return-value]


def _safe_ratio_percent(value: float, reference: float) -> float | None:
    if math.isclose(reference, 0.0):
        return None
    return (value / reference) * 100.0


def _safe_change_percent(value: float, reference: float) -> float | None:
    if math.isclose(reference, 0.0):
        return None
    return ((value - reference) / reference) * 100.0


def _require_float(value: object, *, label: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric, not boolean.")
    if isinstance(value, int | float | str):
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be convertible to float, got {value!r}.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} must be finite, got {value!r}.")
        return number
    raise TypeError(f"{label} must be numeric or numeric text, got {type(value).__name__}.")


def _append_optional_float(values: list[float], value: object) -> None:
    if value is None:
        return
    values.append(_require_float(value, label="optional numeric metric"))


def _basic_stats(values: Sequence[float]) -> JsonDict:
    if not values:
        return {
            "count": 0,
            "average": None,
            "std_dev": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(values),
        "average": statistics.fmean(values),
        "std_dev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _nested_mapping(payload: Mapping[str, object], first_key: str, second_key: str) -> Mapping[str, object]:
    first = payload.get(first_key)
    if not isinstance(first, Mapping):
        raise ValueError(f"Expected mapping at key '{first_key}'.")

    second = first.get(second_key)
    if not isinstance(second, Mapping):
        raise ValueError(f"Expected mapping at key '{first_key}.{second_key}'.")

    return second


__all__ = [
    "_validate_metric_inputs",
    "_load_metrics",
    "_build_metric_point",
    "_compare_metric_group",
    "_build_statistics",
    "_require_mapping",
    "_safe_ratio_percent",
    "_safe_change_percent",
    "_require_float",
    "_append_optional_float",
    "_basic_stats",
    "_nested_mapping",
]
