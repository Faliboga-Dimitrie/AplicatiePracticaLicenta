from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping

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
        - a local filesystem path for backend/internal use,
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

__all__ = [
    "ArtifactKind",
    "ArtifactRef",
    "normalize_artifact_kind",
    "guess_mime_type",
]
