from functools import lru_cache

from ..project_core import settings
from ..access_control import (
    AccessControlService,
    DatabaseConfig,
    ProjectCaseWorkspaceGateway,
)


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