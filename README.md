# Brain MRI Processing and 3D Visualization Application

This project is a practical application for brain MRI preprocessing, tissue segmentation, 3D reconstruction, visualization, and time-based comparison of MRI cases.

The application is composed of:

- a **FastAPI backend**, responsible for authentication, subjects, MRI cases, preprocessing jobs, generated artifacts, and time comparison logic;
- a **React/TypeScript frontend**, responsible for the user interface, MRI upload, processing controls, 3D visualization, and statistical results;
- an **MRI preprocessing pipeline**, which uses **HD-BET** for brain extraction and **FSL**, through Docker, for reorientation and tissue segmentation.

## 1. General requirements

To run the application locally, the following tools are required:

- Python 3.12 or newer;
- Node.js and npm;
- MySQL Server;
- Docker Desktop or Docker Engine;
- HD-BET available in the active Python environment or in the system `PATH`;
- the Docker image `brainlife/fsl:latest`;
- the MNI template file `MNI152_T1_1mm.nii.gz` placed inside the `mni_template` directory.

The relevant project structure is:

```text
AplicatiePracticaLicenta/
├─ frontend/
├─ input_mri/
├─ processed_mri/
├─ mni_template/
│  └─ MNI152_T1_1mm.nii.gz
└─ python_scripts/
   ├─ api/
   ├─ access_control/
   ├─ mesh_analysis/
   ├─ mri_preprocessing/
   └─ project_core/
```

The application should be opened from the project root directory, named `AplicatiePracticaLicenta`. This is important because the backend builds paths to `input_mri`, `processed_mri`, and `mni_template` relative to the project root.

## 2. Backend requirements

The backend uses the following Python packages:

```text
fastapi
uvicorn[standard]
python-multipart
mysql-connector-python
nibabel
numpy
scipy
scikit-image
trimesh
pytest
```

Their main roles are:

- `fastapi` - backend API framework;
- `uvicorn[standard]` - ASGI server used to run the FastAPI application;
- `python-multipart` - required for file uploads through `FormData`;
- `mysql-connector-python` - MySQL database connection;
- `nibabel` - reading and writing NIfTI MRI files;
- `numpy` - numerical operations on MRI and PVE volumes;
- `scipy` - numerical processing, interpolation, and KD-tree based operations;
- `scikit-image` - mesh reconstruction through `marching_cubes`;
- `trimesh` - mesh manipulation and GLB export;
- `pytest` - running the test suite.

The packages can be installed from a terminal opened in the project root:

```powershell
python -m pip install --upgrade pip
python -m pip install fastapi "uvicorn[standard]" python-multipart mysql-connector-python nibabel numpy scipy scikit-image trimesh pytest
```

Optionally, a virtual environment can be created before installing the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install fastapi "uvicorn[standard]" python-multipart mysql-connector-python nibabel numpy scipy scikit-image trimesh pytest
```

## 3. External MRI processing requirements

The preprocessing pipeline depends on two external tools:

```text
HD-BET
FSL through Docker
```

HD-BET must be installed so that the `hd-bet` executable can be found by the application. The backend searches for it in the active Python environment, in the environment `Scripts` directory, and in the system `PATH`.

FSL is executed through Docker by using the following image:

```powershell
docker pull brainlife/fsl:latest
```

Docker must be running before starting an MRI processing job. The application mainly uses FSL for MRI reorientation and FAST tissue segmentation.

In the current configuration, HD-BET is set to run on CUDA:

```text
hd_bet_device = "cuda"
```

If the application is used on a system without a CUDA-compatible GPU, this value should be changed to `cpu` in:

```text
python_scripts/project_core/config.py
```

## 4. Database requirements

The application uses MySQL to store users, subjects, MRI cases, permissions, refresh tokens, and processing-related metadata.

The default database configuration is:

```text
host: 127.0.0.1
port: 3306
user: root
password: ""
database: brain_mri_app
charset: utf8mb4
```

Before starting the backend, MySQL Server must be running.

The application creates the required database tables automatically when the backend starts, as long as the configured MySQL user has the required permissions.

If a different MySQL user, password, host, or database name is used, the configuration must be updated in:

```text
python_scripts/access_control/config.py
```

## 5. Frontend requirements

The frontend is built with React, TypeScript, and Vite.

The main frontend dependencies are:

```text
react
react-dom
three
@react-three/fiber
@react-three/drei
jszip
```

The development dependencies are:

```text
typescript
vite
@vitejs/plugin-react
eslint
@eslint/js
eslint-plugin-react-hooks
eslint-plugin-react-refresh
typescript-eslint
globals
@types/node
@types/react
@types/react-dom
```

These dependencies are installed automatically from `package.json` by running:

```powershell
npm install
```

The frontend also needs an `.env` file inside the `frontend` directory. For local development, it should contain:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

If only `.env.example` exists, copy it and rename the copy to `.env`.

## 6. Running the application

The application must be started from two separate terminals:

- one terminal for the backend;
- one terminal for the frontend.

### 6.1. Start the backend

Open the first terminal in the project root:

```powershell
cd path\to\AplicatiePracticaLicenta
```

If a virtual environment is used, activate it first:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then start the backend with:

```powershell
uvicorn python_scripts.api.main:app --reload
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

The interactive FastAPI documentation will be available at:

```text
http://127.0.0.1:8000/docs
```

Important: the backend command must be executed from the project root directory `AplicatiePracticaLicenta`, not from `python_scripts` and not from `python_scripts/api`.

### 6.2. Start the frontend

Open a second terminal, also from the project root:

```powershell
cd path\to\AplicatiePracticaLicenta
```

Go to the frontend directory:

```powershell
cd .\frontend\
```

On the first run, install the frontend dependencies:

```powershell
npm install
```

Then start the frontend:

```powershell
npm start
```

The frontend will start on the first available local port configured by the Vite development script. Usually, it will be available at:

```text
http://localhost:5173
```

If port `5173` is already in use, the startup script may try other local ports such as `3000`, `3001`, `3002`, `3003`, `3004`, or `3005`.

## 7. Recommended startup order

The recommended order for running the application is:

1. Start MySQL Server.
2. Start Docker Desktop or Docker Engine.
3. Make sure the file `mni_template/MNI152_T1_1mm.nii.gz` exists.
4. Open the first terminal in the project root and start the backend:

```powershell
uvicorn python_scripts.api.main:app --reload
```

5. Open the second terminal in the project root, enter the frontend directory, install dependencies if needed, and start the frontend:

```powershell
cd .\frontend\
npm install
npm start
```

6. Open the frontend in the browser at the URL displayed in the terminal.

## 8. Common issues

### The backend cannot find `python_scripts.*` modules

The backend command was probably executed from the wrong directory. It must be executed from the project root:

```powershell
cd path\to\AplicatiePracticaLicenta
uvicorn python_scripts.api.main:app --reload
```

### File upload does not work

Make sure `python-multipart` is installed:

```powershell
python -m pip install python-multipart
```

### The backend cannot connect to MySQL

Make sure MySQL Server is running and that the configuration in the following file matches the local MySQL installation:

```text
python_scripts/access_control/config.py
```

### MRI processing fails during the FSL step

Make sure Docker is running and that the FSL Docker image is available locally:

```powershell
docker images
```

If the image is missing, pull it with:

```powershell
docker pull brainlife/fsl:latest
```

### MRI processing fails during the HD-BET step

Make sure the `hd-bet` executable is available in the active Python environment:

```powershell
hd-bet -h
```

If the system does not have a CUDA-compatible GPU, change the HD-BET device to `cpu` in:

```text
python_scripts/project_core/config.py
```
