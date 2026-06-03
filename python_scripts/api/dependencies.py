from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..project_core import settings
from ..access_control import (
    AccessControlService,
    DatabaseConfig,
    ProjectCaseWorkspaceGateway,
    UserRecord,
)
from .services import (
    ArtifactService,
    AuthService,
    CaseService,
    JobService,
    FullProcessingService,
    MeshAnalysisService,
    PreprocessingService,
    PublicProcessingService,
    StatisticsService,
    SubjectService,
    TokenService,
    build_default_artifact_service,
    build_default_full_processing_service,
    build_default_job_service,
    build_default_mesh_analysis_service,
    build_default_preprocessing_service,
    build_default_statistics_service,
    build_default_token_service,
)

from .services.factories import build_default_public_processing_service

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_settings():
    return settings


@lru_cache
def get_access_service() -> AccessControlService:
    workspace_gateway = ProjectCaseWorkspaceGateway(settings)
    service = AccessControlService(
        DatabaseConfig(),
        workspace_gateway=workspace_gateway,
    )
    service.ensure_storage()
    return service


@lru_cache
def get_token_service() -> TokenService:
    return build_default_token_service()


@lru_cache
def get_job_service() -> JobService:
    return build_default_job_service()


def get_auth_service(
    access: AccessControlService = Depends(get_access_service),
    token_service: TokenService = Depends(get_token_service),
) -> AuthService:
    return AuthService(access, token_service)


def get_subject_service(
    access: AccessControlService = Depends(get_access_service),
) -> SubjectService:
    return SubjectService(access)



def get_case_service(
    access: AccessControlService = Depends(get_access_service),
) -> CaseService:
    return CaseService(access)


def get_preprocessing_service(
    cases: CaseService = Depends(get_case_service),
    jobs: JobService = Depends(get_job_service),
) -> PreprocessingService:
    return build_default_preprocessing_service(
        cases=cases,
        jobs=jobs,
        settings_obj=settings,
    )


def get_full_processing_service(
    cases: CaseService = Depends(get_case_service),
    jobs: JobService = Depends(get_job_service),
) -> FullProcessingService:
    return build_default_full_processing_service(
        cases=cases,
        jobs=jobs,
        settings_obj=settings,
    )


def get_mesh_analysis_service(
    cases: CaseService = Depends(get_case_service),
    jobs: JobService = Depends(get_job_service),
) -> MeshAnalysisService:
    return build_default_mesh_analysis_service(
        cases=cases,
        jobs=jobs,
        settings_obj=settings,
    )



@lru_cache
def get_public_processing_service() -> PublicProcessingService:
    return build_default_public_processing_service(settings_obj=settings)


def get_statistics_service(
    cases: CaseService = Depends(get_case_service),
) -> StatisticsService:
    return build_default_statistics_service(cases=cases)

def get_artifact_service(
    cases: CaseService = Depends(get_case_service),
) -> ArtifactService:
    return build_default_artifact_service(
        cases=cases,
        settings_obj=settings,
    )

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    auth: AuthService = Depends(get_auth_service),
) -> UserRecord:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = auth.get_current_user(credentials.credentials)
    if not result.success or result.data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.error or "Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result.data
