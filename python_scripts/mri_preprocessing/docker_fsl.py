from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


class FslDockerRunner:
    """
    Small Python wrapper around `docker run` for the FSL commands used by the
    preprocessing package.

    This replaces the previous Python -> PowerShell -> Docker chain with a
    Python -> Docker chain, keeping Docker-specific command construction in one
    place while still avoiding a hard dependency on the Docker Python SDK.
    """

    def __init__(
        self,
        docker_image: str,
        docker_executable: str = "docker",
    ) -> None:
        self.docker_image = str(docker_image)
        self.docker_executable = docker_executable

    def build_reorient_command(
        self,
        input_path: Path,
        output_path: Path,
        *,
        container_input_dir: str = "/data/in",
        container_output_dir: str = "/data/out",
    ) -> list[str]:
        input_path = Path(input_path).resolve(strict=True)
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        env = {
            "INPUT_NAME": input_path.name,
            "OUTPUT_NAME": output_path.name,
            "CONTAINER_INPUT_DIR": container_input_dir,
            "CONTAINER_OUTPUT_DIR": container_output_dir,
        }
        volumes = [
            self._volume_arg(input_path.parent, container_input_dir, read_only=True),
            self._volume_arg(output_path.parent, container_output_dir),
        ]
        bash = (
            'set -euo pipefail\n'
            'fslreorient2std '
            '"$CONTAINER_INPUT_DIR/$INPUT_NAME" '
            '"$CONTAINER_OUTPUT_DIR/$OUTPUT_NAME"'
        )

        return self._docker_run_command(env=env, volumes=volumes, bash=bash)

    def build_fast_command(
        self,
        input_path: Path,
        output_prefix: Path,
        *,
        classes: int,
        image_type: int,
        container_input_dir: str,
        container_output_dir: str,
    ) -> list[str]:
        input_path = Path(input_path).resolve(strict=True)
        output_prefix = Path(output_prefix).resolve()
        output_prefix.parent.mkdir(parents=True, exist_ok=True)

        env = {
            "INPUT_NAME": input_path.name,
            "OUTPUT_BASENAME": output_prefix.name,
            "FAST_CLASSES": str(classes),
            "IMAGE_TYPE": str(image_type),
            "CONTAINER_INPUT_DIR": container_input_dir,
            "CONTAINER_OUTPUT_DIR": container_output_dir,
        }
        volumes = [
            self._volume_arg(input_path.parent, container_input_dir, read_only=True),
            self._volume_arg(output_prefix.parent, container_output_dir),
        ]
        bash = (
            'set -euo pipefail\n'
            'fast '
            '-t "$IMAGE_TYPE" '
            '-n "$FAST_CLASSES" '
            '-o "$CONTAINER_OUTPUT_DIR/$OUTPUT_BASENAME" '
            '"$CONTAINER_INPUT_DIR/$INPUT_NAME"'
        )

        return self._docker_run_command(env=env, volumes=volumes, bash=bash)

    def run(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self._require_docker_available()
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )

    def _docker_run_command(
        self,
        *,
        env: Mapping[str, str],
        volumes: Sequence[str],
        bash: str,
    ) -> list[str]:
        cmd = [self.docker_executable, "run", "--rm"]

        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])

        for volume in volumes:
            cmd.extend(["-v", volume])

        cmd.extend([self.docker_image, "bash", "-lc", bash])
        return cmd

    def _require_docker_available(self) -> None:
        if shutil.which(self.docker_executable) is None:
            raise RuntimeError(
                f"Docker executable not found: {self.docker_executable!r}. "
                "Install Docker Desktop/Engine or make sure Docker is available on PATH."
            )

    @staticmethod
    def _volume_arg(
        host_path: Path,
        container_path: str,
        *,
        read_only: bool = False,
    ) -> str:
        host = str(Path(host_path).resolve())
        mode = ":ro" if read_only else ""
        return f"{host}:{container_path}{mode}"


__all__ = ["FslDockerRunner"]
