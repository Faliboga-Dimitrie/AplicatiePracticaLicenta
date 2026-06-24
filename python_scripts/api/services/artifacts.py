from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ...access_control import DbResult, MriCaseRecord, UserRecord
from ...project_core.artifacts import (
    ArtifactKind,
    ArtifactRef,
    guess_mime_type,
)
from ...project_core.domain import MRICase
from ...project_core.ports import WorkspaceProvider
from .cases import CaseService


@dataclass(frozen=True)
class ArtifactFile:
    """
    Internal API artifact representation.

    ArtifactRef is the public/domain object returned to React. This wrapper also
    keeps the local path needed by FileResponse, but serialization deliberately
    does not expose that filesystem path.
    """

    ref: ArtifactRef
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class CaseArtifactBundle:
    """Downloadable artifacts discovered for one authorized MRI case."""

    case_db_id: int
    subject_id: str
    acquisition_date: date
    case_key: str
    artifacts: tuple[ArtifactFile, ...]


class ArtifactService:
    """
    Web-facing artifact service.

    Only final user-facing outputs are published: GLB 3D models and JSON metrics.
    Processing intermediates can still exist on disk for the scientific pipeline,
    but they are never treated as downloadable artifacts by this service.

    React sees stable URLs like:

        /cases/12/artifacts/gm_mesh.glb
        /cases/12/artifacts/metrics.json

    The URL path parameter is matched only against this discovered manifest, so
    file serving does not expose arbitrary local paths.
    """

    def __init__(
        self,
        *,
        cases: CaseService,
        workspace_provider: WorkspaceProvider,
    ):
        self.cases = cases
        self.workspace_provider = workspace_provider

    def list_for_case(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[CaseArtifactBundle]:
        case_result = self.cases.get_for_user(
            user,
            case_id,
        )
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        try:
            bundle = self._build_bundle(case_result.data)
            return DbResult.ok(bundle)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_file_for_case(
        self,
        user: UserRecord,
        case_id: int,
        artifact_name: str,
    ) -> DbResult[ArtifactFile]:
        bundle_result = self.list_for_case(user, case_id)
        if not bundle_result.success:
            return DbResult.fail(bundle_result.error or "Could not load case artifacts.")
        if bundle_result.data is None:
            return DbResult.ok(None)

        normalized_name = artifact_name.strip()
        for artifact in bundle_result.data.artifacts:
            if artifact.ref.name == normalized_name:
                return DbResult.ok(artifact)

        return DbResult.ok(None)

    def _build_bundle(self, case: MriCaseRecord) -> CaseArtifactBundle:
        workspace = case.workspace
        if workspace is None:
            domain_case = MRICase(
                subject_id=case.subject_id,
                acquisition_date=case.acquisition_date.isoformat(),
                raw_path=Path(f"{case.subject_id}.nii.gz"),
            )
            workspace = self.workspace_provider.get_workspace(domain_case)

        artifacts: list[ArtifactFile] = []
        seen_paths: set[Path] = set()
        used_names: set[str] = set()

        def add_if_present(
            *,
            name: str,
            kind: ArtifactKind,
            path: Path,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            artifact = self._known_file(
                case_id=case.id,
                name=self._unique_name(name, used_names),
                kind=kind,
                path=path,
                metadata=metadata,
            )
            if artifact is None:
                return
            resolved = artifact.path.resolve()
            if resolved in seen_paths:
                return
            seen_paths.add(resolved)
            used_names.add(artifact.ref.name)
            artifacts.append(artifact)

        for tissue, path in workspace.mesh_paths.items():
            add_if_present(
                name=f"{tissue}_mesh.glb",
                kind=ArtifactKind.MESH,
                path=path,
                metadata={"tissue": tissue},
            )

        add_if_present(
            name="metrics.json",
            kind=ArtifactKind.METRICS,
            path=workspace.metrics_json_path,
        )

        return CaseArtifactBundle(
            case_db_id=case.id,
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
            case_key=case.case_key,
            artifacts=tuple(artifacts),
        )

    def _known_file(
        self,
        *,
        case_id: int,
        name: str,
        kind: ArtifactKind,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactFile | None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return None

        if not self._is_public_artifact_path(path):
            return None

        stat = path.stat()
        public_metadata: dict[str, Any] = {
            "size_bytes": stat.st_size,
        }
        if metadata:
            public_metadata.update(metadata)

        ref = ArtifactRef(
            name=name,
            kind=kind,
            uri=self._artifact_url(case_id, name),
            mime_type=guess_mime_type(path, kind),
            metadata=public_metadata,
        )
        return ArtifactFile(
            ref=ref,
            path=path.resolve(),
            size_bytes=stat.st_size,
        )

    def public_bundle_dict(self, bundle: CaseArtifactBundle) -> dict[str, Any]:
        """Return the frontend-safe artifact payload used by job results."""
        return {
            "case_id": bundle.case_db_id,
            "case_key": bundle.case_key,
            "subject_id": bundle.subject_id,
            "acquisition_date": bundle.acquisition_date.isoformat(),
            "artifacts": [
                self.public_artifact_dict(artifact)
                for artifact in bundle.artifacts
            ],
        }

    def public_artifact_dict(self, artifact: ArtifactFile) -> dict[str, Any]:
        ref = artifact.ref
        return {
            "name": ref.name,
            "kind": ref.kind.value,
            "url": ref.uri,
            "mime_type": ref.mime_type,
            "size_bytes": artifact.size_bytes,
            "metadata": dict(ref.metadata or {}),
        }

    def _artifact_url(self, case_id: int, artifact_name: str) -> str:
        return f"/cases/{case_id}/artifacts/{quote(artifact_name, safe='')}"

    def _is_public_artifact_name(self, name: str) -> bool:
        lower = name.lower()
        return lower.endswith(".glb") or lower.endswith(".json")

    def _is_public_artifact_path(self, path: Path) -> bool:
        return path.exists() and path.is_file() and self._is_public_artifact_name(path.name)

    def _artifact_kind_for_path(self, path: Path) -> ArtifactKind | None:
        lower = path.name.lower()
        if lower.endswith(".glb"):
            return ArtifactKind.MESH
        if lower.endswith(".json"):
            return ArtifactKind.METRICS
        return None

    def _artifact_metadata_from_filename(self, path: Path) -> dict[str, Any]:
        lower = path.name.lower()
        metadata: dict[str, Any] = {}
        if lower.endswith(".glb"):
            if "csf" in lower:
                metadata["tissue"] = "csf"
            elif "gm" in lower or "gray" in lower or "grey" in lower:
                metadata["tissue"] = "gm"
            elif "wm" in lower or "white" in lower:
                metadata["tissue"] = "wm"
        return metadata

    def _unique_name(self, preferred: str, used_names: set[str]) -> str:
        if preferred not in used_names:
            return preferred

        path = Path(preferred)
        stem = path.stem
        suffix = path.suffix
        index = 2
        while True:
            candidate = f"{stem}_{index}{suffix}"
            if candidate not in used_names:
                return candidate
            index += 1


__all__ = ["ArtifactFile", "ArtifactService", "CaseArtifactBundle"]
