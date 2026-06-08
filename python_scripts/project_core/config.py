from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    # --- project roots ---
    input_mri_dir: Path
    processed_mri_dir: Path
    mni_template_dir: Path

    # --- processed stage folders ---
    reoriented_dir: Path
    hd_bet_dir: Path
    fast_dir: Path
    mesh_dir: Path

    # --- template paths ---
    mni_template_path: Path

    # --- Docker / external tool config ---
    fsl_docker_image: str
    container_input_dir: str
    container_output_dir: str

    # --- processing parameters ---
    fast_classes: int = 3
    overwrite: bool = True
    skip_existing: bool = True
    hd_bet_device: str = "cuda"
    hd_bet_verbose: bool = True
    hd_bet_executable: str | None = None

def build_settings() -> Settings:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    python_scripts_dir = package_dir.parent
    project_root = python_scripts_dir.parent

    input_mri_dir = project_root / "input_mri"
    processed_mri_dir = project_root / "processed_mri"
    mni_template_dir = project_root / "mni_template"

    return Settings(
        input_mri_dir=input_mri_dir,
        processed_mri_dir=processed_mri_dir,
        mni_template_dir=mni_template_dir,

        reoriented_dir=processed_mri_dir / "reoriented",
        hd_bet_dir=processed_mri_dir / "hd_bet",
        fast_dir=processed_mri_dir / "fast",
        mesh_dir=processed_mri_dir / "meshes",

        mni_template_path=mni_template_dir / "MNI152_T1_1mm.nii.gz",

        fsl_docker_image="brainlife/fsl:latest",
        container_input_dir="/data/in",
        container_output_dir="/data/out",
    )


settings = build_settings()

def ensure_main_directories(settings: Settings) -> None:
    for path in [
        settings.input_mri_dir,
        settings.processed_mri_dir,
        settings.reoriented_dir,
        settings.hd_bet_dir,
        settings.fast_dir,
        settings.mni_template_dir,
        settings.mesh_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)