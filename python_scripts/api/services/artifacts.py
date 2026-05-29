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
    StoredCaseResult,
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
    """Artifacts discovered for one authorized MRI case."""

    case_db_id: int
    subject_id: str
    acquisition_date: date
    case_key: str
    artifacts: tuple[ArtifactFile, ...]

    @property
    def stored_result(self) -> StoredCaseResult:
        return StoredCaseResult(
            subject_id=self.subject_id,
            acquisition_date=self.acquisition_date.isoformat(),
            artifacts=tuple(artifact.ref for artifact in self.artifacts),
        )


class ArtifactService:
    """
    Web-facing artifact service.

    This service turns the files known by CaseWorkspace into frontend-safe
    ArtifactRef objects and FileResponse-ready paths. React sees stable URLs like:

        /cases/12/artifacts/csf_mesh.glb

    It never receives raw local filesystem paths. File serving is also safe
    because get_file_for_case only returns files from the known workspace artifact
    manifest, not an arbitrary path provided by the client.
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
            minimum_role="viewer",
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

    def list_viewer_for_case(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[CaseArtifactBundle]:
        """Return only artifacts needed by the interactive 3D viewer.

        The normal artifact endpoint intentionally lists everything useful for
        download/debugging. The viewer should be narrower: GLB meshes, GLB
        wireframes and the metrics JSON reference. This avoids React considering
        QC images or NIfTI files when opening the WebGL page.
        """
        bundle_result = self.list_for_case(user, case_id)
        if not bundle_result.success:
            return DbResult.fail(bundle_result.error or "Could not load case artifacts.")
        if bundle_result.data is None:
            return DbResult.ok(None)

        viewer_kinds = {
            ArtifactKind.MESH,
            ArtifactKind.WIREFRAME,
            ArtifactKind.METRICS,
        }
        viewer_artifacts = tuple(
            artifact
            for artifact in bundle_result.data.artifacts
            if artifact.ref.kind in viewer_kinds
        )

        return DbResult.ok(
            CaseArtifactBundle(
                case_db_id=bundle_result.data.case_db_id,
                subject_id=bundle_result.data.subject_id,
                acquisition_date=bundle_result.data.acquisition_date,
                case_key=bundle_result.data.case_key,
                artifacts=viewer_artifacts,
            )
        )

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

        # Main 3D display outputs.
        for tissue, path in workspace.mesh_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"{tissue}_mesh.glb",
                    kind=ArtifactKind.MESH,
                    path=path,
                    metadata={"tissue": tissue},
                )
            )

        for tissue, path in workspace.wireframe_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"{tissue}_wireframe.glb",
                    kind=ArtifactKind.WIREFRAME,
                    path=path,
                    metadata={"tissue": tissue},
                )
            )

        artifacts.append(
            self._known_file(
                case_id=case.id,
                name="metrics.json",
                kind=ArtifactKind.METRICS,
                path=workspace.mesh_metrics_json_path,
            )
        )

        # QC images are useful for a React results/debug page when generated.
        for qc_name, path in workspace.qc_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"qc_{qc_name}.png",
                    kind=ArtifactKind.QC_IMAGE,
                    path=path,
                    metadata={"stage": qc_name},
                )
            )

        # Preprocessing outputs are not the main browser display target, but they
        # are useful for debugging/downloads and make the artifact list complete.
        preprocessing_outputs: list[tuple[str, Path, dict[str, Any]]] = [
            ("reoriented.nii.gz", workspace.reoriented_path, {"stage": "reorientation"}),
            ("skull_stripped.nii.gz", workspace.skull_stripped_path, {"stage": "hd_bet"}),
            ("skull_stripped_mask.nii.gz", workspace.skull_stripped_mask_path, {"stage": "hd_bet", "mask": True}),
            ("fast_seg.nii.gz", workspace.fast_seg_path, {"stage": "fast"}),
            ("fast_pveseg.nii.gz", workspace.fast_pve_seg_path, {"stage": "fast"}),
        ]
        for tissue, path in workspace.fast_pve_paths.items():
            preprocessing_outputs.append(
                (f"fast_pve_{tissue}.nii.gz", path, {"stage": "fast", "tissue": tissue})
            )

        for name, path, metadata in preprocessing_outputs:
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=name,
                    kind=ArtifactKind.NIFTI,
                    path=path,
                    metadata=metadata,
                )
            )

        existing_artifacts = tuple(artifact for artifact in artifacts if artifact is not None)
        return CaseArtifactBundle(
            case_db_id=case.id,
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
            case_key=case.case_key,
            artifacts=existing_artifacts,
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
        """Return the frontend-safe artifact payload used by job results.

        This intentionally mirrors the /cases/{case_id}/artifacts response, but
        avoids importing API serializers into the service layer. No local
        filesystem paths are exposed.
        """
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


__all__ = ["ArtifactFile", "ArtifactService", "CaseArtifactBundle"]
