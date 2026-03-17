from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    # --- project roots ---
    project_root: Path
    input_mri_dir: Path
    processed_mri_dir: Path
    python_scripts_dir: Path
    shell_scripts_dir: Path
    mni_template_dir: Path

    # --- processed stage folders ---
    reoriented_dir: Path
    hd_bet_dir: Path
    fast_dir: Path
    qc_dir: Path

    # --- shell script paths ---
    reorient_script: Path
    fast_script: Path

    # --- template paths ---
    mni_template_path: Path

    # --- Docker / external tool config ---
    fsl_docker_image: str
    container_input_dir: str
    container_output_dir: str
    container_mni_path: str

    # --- processing parameters ---
    fast_classes: int = 3
    overwrite: bool = False
    skip_existing: bool = True
    hd_bet_device: str = "cuda"
    hd_bet_verbose: bool = True
    fast_verbose: bool = True

    # --- naming suffixes ---
    reoriented_suffix: str = "_reo"
    bet_suffix: str = "_bet"
    bet_mask_suffix: str = "_bet_mask"

    # --- QC parameters ---
    generate_qc: bool = True
    fail_on_qc_error: bool = False


def build_settings() -> Settings:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    python_scripts_dir = package_dir.parent
    project_root = python_scripts_dir.parent

    input_mri_dir = project_root / "input_mri"
    processed_mri_dir = project_root / "processed_mri"
    shell_scripts_dir = project_root / "shell_scripts"
    mni_template_dir = project_root / "mni_template"

    return Settings(
        project_root=project_root,
        input_mri_dir=input_mri_dir,
        processed_mri_dir=processed_mri_dir,
        python_scripts_dir=python_scripts_dir,
        shell_scripts_dir=shell_scripts_dir,
        mni_template_dir=mni_template_dir,

        reoriented_dir=processed_mri_dir / "reoriented",
        hd_bet_dir=processed_mri_dir / "hd_bet",
        fast_dir=processed_mri_dir / "fast",
        qc_dir=processed_mri_dir / "qc",

        reorient_script=shell_scripts_dir / "t1_preprocessing" / "docker_reorient.ps1",
        fast_script=shell_scripts_dir / "t1_preprocessing" / "docker_fast.ps1",

        mni_template_path=mni_template_dir / "MNI152_T1_1mm.nii.gz",

        fsl_docker_image="brainlife/fsl:latest",
        container_input_dir="/data/in",
        container_output_dir="/data/out",
        container_mni_path="/usr/share/fsl/data/standard/MNI152_T1_1mm.nii.gz",
    )


settings = build_settings()

def ensure_main_directories(settings: Settings) -> None:
    for path in [
        settings.input_mri_dir,
        settings.processed_mri_dir,
        settings.reoriented_dir,
        settings.hd_bet_dir,
        settings.fast_dir,
        settings.qc_dir,
        settings.mni_template_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)