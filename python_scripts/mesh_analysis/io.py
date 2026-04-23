import nibabel as nb
from ..project_core import CasePaths

def load_fast_pves(paths: CasePaths) -> dict[str, nb.Nifti1Image]:
    return {
        tissue: nb.load(str(pve_path))
        for tissue, pve_path in paths.fast_pve_paths.items()
    }

def load_fast_pveseg(paths: CasePaths) -> nb.Nifti1Image:
    """
    Load the FAST-produced pveseg image for one case.
    Returns a Nifti1Image object.
    """
    pveseg_path = paths.fast_pve_seg_path
    img = nb.load(pveseg_path)
    return img