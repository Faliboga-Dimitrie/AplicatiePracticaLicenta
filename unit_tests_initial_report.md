# Initial backend unit tests

Implemented a first focused pytest suite for:

- `project_core`
- `mri_preprocessing`
- `mesh_analysis`

The tests follow the Arrange / Act / Assert style where it is practical.

## Test structure

```text
backend_root/
  pytest.ini
  tests/
    conftest.py
    project_core/
      test_workspace.py
    mri_preprocessing/
      test_segmentation.py
    mesh_analysis/
      test_analysis.py
```

## Notes

The backend packages use parent-relative imports between sibling packages. When the archives are extracted directly as sibling folders, `tests/conftest.py` creates a lightweight package alias named `backend_under_test` so the tests can import modules without changing application code.

`conftest.py` also installs a minimal `nibabel` stub only if real `nibabel` is not installed. This lets orchestration/mocking tests run in lightweight CI. In the real project environment, where `nibabel` is installed, the real package is used.

## Tests added

### `project_core`

- validates canonical workspace path construction;
- validates FAST PVE path naming;
- validates input-file copying and overwrite behavior;
- validates deleting processed outputs while preserving input;
- validates staged-delete rollback and commit behavior;
- validates subject-level workspace deletion;
- validates invalid acquisition-date rejection.

### `mri_preprocessing`

- validates FAST PowerShell command construction;
- validates that complete existing PVE outputs skip FAST execution;
- validates FAST cleanup removes `_mixeltype`, `_seg`, and `_pveseg` outputs while keeping PVE files;
- validates full segmentation flow with a fake FAST runner and post-run cleanup;
- validates missing required PVE outputs raise an error.

### `mesh_analysis`

- validates PVE-sum volume formula including clipping invalid probability values;
- validates `MeshAnalysisPipeline` uses injected strategies and writes metrics JSON;
- validates existing complete mesh-analysis outputs are loaded without rerunning strategies;
- validates missing FAST PVE outputs fail early.

## Validation result

```text
pytest -q
15 passed
```
