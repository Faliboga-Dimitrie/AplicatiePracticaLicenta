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

    # --- processed stage folders ---
    reoriented_dir: Path
    hd_bet_dir: Path
    fast_dir: Path
    registration_dir: Path
    atlas_mapping_dir: Path
    qc_dir: Path

    # --- shell script paths ---
    reorient_script: Path
    fast_script: Path
    registration_script: Path
    atlas_mapping_script: Path

    # --- Docker / external tool config ---
    fsl_docker_image: str
    container_input_dir: str
    container_output_dir: str
    container_mni_path: str
    container_ho_cort_path: str
    container_ho_sub_path: str

    # --- processing parameters ---
    fast_classes: int = 3
    overwrite: bool = False
    skip_existing: bool = True
    hd_bet_device: str = "cuda"

    # --- naming suffixes ---
    reoriented_suffix: str = "_reo"
    bet_suffix: str = "_bet"
    bet_mask_suffix: str = "_bet_mask"
    t1_to_mni_aff_suffix: str = "_T1_to_MNI_aff.mat"
    t1_to_mni_warpcoef_suffix: str = "_T1_to_MNI_warpcoef.nii.gz"
    mni_to_t1_warp_suffix: str = "_MNI_to_T1_warp.nii.gz"
    ho_cort_suffix: str = "_HO_cort_thr25_in_T1.nii.gz"
    ho_sub_suffix: str = "_HO_sub_thr25_in_T1.nii.gz"


def build_settings() -> Settings:
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    python_scripts_dir = package_dir.parent
    project_root = python_scripts_dir.parent

    input_mri_dir = project_root / "input_mri"
    processed_mri_dir = project_root / "processed_mri"
    shell_scripts_dir = project_root / "shell_scripts"

    return Settings(
        project_root=project_root,
        input_mri_dir=input_mri_dir,
        processed_mri_dir=processed_mri_dir,
        python_scripts_dir=python_scripts_dir,
        shell_scripts_dir=shell_scripts_dir,

        reoriented_dir=processed_mri_dir / "reoriented",
        hd_bet_dir=processed_mri_dir / "hd_bet",
        fast_dir=processed_mri_dir / "fast",
        registration_dir=processed_mri_dir / "registration",
        atlas_mapping_dir=processed_mri_dir / "atlas_mapping",
        qc_dir=processed_mri_dir / "qc",

        reorient_script=shell_scripts_dir / "t1_preprocessing" / "docker_reorient.ps1",
        fast_script=shell_scripts_dir / "t1_preprocessing" / "docker_fast.ps1",
        registration_script=shell_scripts_dir / "t1_preprocessing" / "docker_registration.ps1",
        atlas_mapping_script=shell_scripts_dir / "t1_preprocessing" / "docker_atlas_mapping.ps1",

        fsl_docker_image="fsl-local:latest",
        container_input_dir="/data/in",
        container_output_dir="/data/out",
        container_mni_path="/usr/share/fsl/data/standard/MNI152_T1_1mm.nii.gz",
        container_ho_cort_path="/usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-1mm.nii.gz",
        container_ho_sub_path="/usr/share/data/harvard-oxford-atlases/HarvardOxford/HarvardOxford-sub-maxprob-thr25-1mm.nii.gz",
    )


settings = build_settings()

def ensure_main_directories(settings: Settings) -> None:
    for path in [
        settings.input_mri_dir,
        settings.processed_mri_dir,
        settings.reoriented_dir,
        settings.hd_bet_dir,
        settings.fast_dir,
        settings.registration_dir,
        settings.atlas_mapping_dir,
        settings.qc_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)