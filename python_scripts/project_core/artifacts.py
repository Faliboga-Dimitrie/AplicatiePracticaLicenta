from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping


class ArtifactKind(str, Enum):
    """Downloadable artifact categories exposed by the API."""

    MESH = "mesh"
    METRICS = "metrics"


@dataclass(frozen=True)
class ArtifactRef:
    """
    Reference to a final downloadable result.

    The application exposes only two artifact file types:
    - GLB 3D models (`ArtifactKind.MESH`)
    - JSON measurement payloads (`ArtifactKind.METRICS`)
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
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ArtifactKind)
        raise ValueError(f"Unsupported downloadable artifact kind '{kind}'. Expected one of: {allowed}.") from exc


def guess_mime_type(path: Path, kind: ArtifactKind | str | None = None) -> str | None:
    """Return MIME type only for published GLB/JSON artifacts."""
    if kind is not None:
        normalize_artifact_kind(kind)

    name = path.name.lower()

    if name.endswith(".glb"):
        return "model/gltf-binary"
    if name.endswith(".json"):
        return "application/json"

    return None


__all__ = [
    "ArtifactKind",
    "ArtifactRef",
    "normalize_artifact_kind",
    "guess_mime_type",
]
