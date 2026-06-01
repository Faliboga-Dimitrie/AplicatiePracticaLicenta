from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping
from urllib.parse import quote

from .domain import MRICase


class ArtifactKind(str, Enum):
    """
    Public categories for files/results produced by the pipeline.

    These values are API/JSON-friendly and intentionally broader than concrete
    implementation details. For example, a mesh can be produced by marching
    cubes today and by another extractor later while still being a MESH artifact.
    """

    MESH = "mesh"
    METRICS = "metrics"
    NIFTI = "nifti"
    LOG = "log"
    OTHER = "other"


@dataclass(frozen=True)
class ArtifactRef:
    """
    Reference to a final/published artifact.

    `uri` may be:
        - a local filesystem path for CLI use,
        - a static URL path for FastAPI/frontend use,
        - a database/blob-storage URI in a future implementation.
    """

    name: str
    kind: ArtifactKind
    uri: str
    mime_type: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "kind": self.kind.value,
            "uri": self.uri,
        }

        if self.mime_type is not None:
            payload["mime_type"] = self.mime_type

        if self.metadata:
            payload["metadata"] = dict(self.metadata)

        return payload

    @classmethod
    def from_path(
        cls,
        *,
        name: str,
        kind: ArtifactKind | str,
        path: Path,
        mime_type: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> "ArtifactRef":
        return cls(
            name=name,
            kind=normalize_artifact_kind(kind),
            uri=str(path),
            mime_type=mime_type,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class StoredCaseResult:
    """
    Collection of published artifacts for one subject acquisition.
    """

    subject_id: str
    acquisition_date: str | None = None
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    @property
    def case_id(self) -> str:
        if self.acquisition_date is None:
            return self.subject_id
        return f"{self.subject_id}_{self.acquisition_date}"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "subject_id": self.subject_id,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }
        if self.acquisition_date is not None:
            payload["acquisition_date"] = self.acquisition_date
            payload["case_id"] = self.case_id
        return payload

    def by_name(self) -> dict[str, ArtifactRef]:
        return {artifact.name: artifact for artifact in self.artifacts}

    def by_kind(self, kind: ArtifactKind | str) -> list[ArtifactRef]:
        normalized = normalize_artifact_kind(kind)
        return [artifact for artifact in self.artifacts if artifact.kind == normalized]


def normalize_artifact_kind(kind: ArtifactKind | str) -> ArtifactKind:
    if isinstance(kind, ArtifactKind):
        return kind

    value = kind.strip().lower()
    try:
        return ArtifactKind(value)
    except ValueError:
        return ArtifactKind.OTHER


def guess_mime_type(path: Path, kind: ArtifactKind | str = ArtifactKind.OTHER) -> str | None:
    """
    Small explicit MIME map for the artifacts this project produces most often.
    """
    normalized_kind = normalize_artifact_kind(kind)
    name = path.name.lower()

    if name.endswith(".glb"):
        return "model/gltf-binary"
    if name.endswith(".gltf"):
        return "model/gltf+json"
    if name.endswith(".json") or normalized_kind == ArtifactKind.METRICS:
        return "application/json"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".nii") or name.endswith(".nii.gz"):
        return "application/octet-stream"
    if name.endswith(".txt") or normalized_kind == ArtifactKind.LOG:
        return "text/plain"

    return None


def _safe_case_segment(value: str) -> str:
    """
    Keep filesystem names simple and avoid accidental nested paths.
    """
    return value.replace("/", "_").replace("\\", "_").strip()


def _path_suffix(path: Path) -> str:
    """
    Preserve .nii.gz as a double suffix; otherwise use Path.suffix.
    """
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix


def _artifact_filename(artifact_name: str, source_path: Path) -> str:
    safe_name = _safe_case_segment(artifact_name)
    suffix = _path_suffix(source_path)

    if suffix and safe_name.lower().endswith(suffix.lower()):
        return safe_name

    return f"{safe_name}{suffix}"


class FileSystemArtifactStore:
    """
    Default ArtifactStore implementation backed by the local filesystem.

    The store can either:
        - copy final files into an artifact root, or
        - register files in place when copy_files=False.

    For a future FastAPI app, pass a base_uri such as "/static/artifacts" so
    returned ArtifactRef objects contain web-friendly URIs instead of raw paths.
    """

    def __init__(
        self,
        root_dir: Path,
        *,
        base_uri: str | None = None,
        copy_files: bool = True,
    ):
        self.root_dir = Path(root_dir)
        self.base_uri = base_uri.rstrip("/") if base_uri is not None else None
        self.copy_files = copy_files

    def save_file(
        self,
        *,
        case: MRICase,
        source_path: Path,
        artifact_name: str,
        artifact_kind: ArtifactKind | str,
        mime_type: str | None = None,
    ) -> ArtifactRef:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Artifact source file does not exist: {source_path}")
        if not source_path.is_file():
            raise ValueError(f"Artifact source path is not a file: {source_path}")

        kind = normalize_artifact_kind(artifact_kind)
        final_path = self._final_path(case, artifact_name, source_path)

        if self.copy_files:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.resolve() != final_path.resolve():
                shutil.copy2(source_path, final_path)
        else:
            final_path = source_path

        return ArtifactRef(
            name=artifact_name,
            kind=kind,
            uri=self._uri_for(case, final_path),
            mime_type=mime_type or guess_mime_type(final_path, kind),
            metadata={"path": str(final_path)},
        )

    def save_metrics(
        self,
        *,
        case: MRICase,
        metrics: Mapping[str, object],
        artifact_name: str = "metrics",
    ) -> ArtifactRef:
        metrics_path = self._metrics_path(case, artifact_name)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)

        with metrics_path.open("w", encoding="utf-8") as f:
            json.dump(dict(metrics), f, indent=2)

        return ArtifactRef(
            name=artifact_name,
            kind=ArtifactKind.METRICS,
            uri=self._uri_for(case, metrics_path),
            mime_type="application/json",
            metadata={"path": str(metrics_path)},
        )

    def _case_dir(self, case: MRICase) -> Path:
        return (
            self.root_dir
            / _safe_case_segment(case.subject_id)
            / _safe_case_segment(case.acquisition_date)
        )

    def _final_path(self, case: MRICase, artifact_name: str, source_path: Path) -> Path:
        return self._case_dir(case) / _artifact_filename(artifact_name, source_path)

    def _metrics_path(self, case: MRICase, artifact_name: str) -> Path:
        filename = _safe_case_segment(artifact_name)
        if not filename.lower().endswith(".json"):
            filename = f"{filename}.json"
        return self._case_dir(case) / filename

    def _uri_for(self, case: MRICase, path: Path) -> str:
        if self.base_uri is None:
            return str(path)

        # Keep the URI independent of OS path separators.
        subject_segment = quote(_safe_case_segment(case.subject_id))
        date_segment = quote(_safe_case_segment(case.acquisition_date))
        filename = quote(path.name)
        return f"{self.base_uri}/{subject_segment}/{date_segment}/{filename}"


__all__ = [
    "ArtifactKind",
    "ArtifactRef",
    "StoredCaseResult",
    "FileSystemArtifactStore",
    "normalize_artifact_kind",
    "guess_mime_type",
]
