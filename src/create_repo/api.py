"""
FastAPI application with repository management endpoints.
"""

import os
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from create_repo.core import PrivilegeManager
from create_repo.clients import NexusClient, IQServerClient
from create_repo.app_config import AppConfigService
from create_repo.app_config import ValidationError, ConfigurationError
from create_repo.schemas import (
    RepositoryRequest,
    BatchRequest,
    OperationResponse,
    BatchOperationResponse,
)
from create_repo.utils import get_application_path

# --- Application Setup ---

app = FastAPI(
    title="Nexus Repository and Privilege Manager API",
    description="An API to automatically create and manage Nexus repositories and associated privileges.",
    version="1.0.0",
)
security = HTTPBearer()

# Initialize the configuration service once at startup
config_service = AppConfigService("config")


def create_clients():
    """Factory function to create Nexus and IQ Server clients."""
    nexus_creds = config_service.get_nexus_credentials()
    iq_creds = config_service.get_iqserver_credentials()
    package_config = config_service.get_package_manager_config()

    nexus_client = NexusClient(
        nexus_creds.url,
        nexus_creds.username,
        nexus_creds.password,
        package_config.get("supported_formats", {}),
    )

    iq_client = IQServerClient(iq_creds.url, iq_creds.username, iq_creds.password)

    return nexus_client, iq_client


def create_privilege_manager(data: dict, action: str) -> PrivilegeManager:
    """Creates a PrivilegeManager instance with proper dependency injection."""
    operation_config = config_service.create_operation_config(data, action)
    nexus_client, iq_client = create_clients()
    return PrivilegeManager(operation_config, nexus_client, iq_client)


def validate_token(token: str) -> bool:
    """Validates an API token against the one in the environment."""
    return token == os.getenv("API_TOKEN")


# --- Exception Handlers ---


@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc: ValidationError):
    return JSONResponse(status_code=400, content={"success": False, "error": str(exc)})


@app.exception_handler(ConfigurationError)
async def configuration_exception_handler(request, exc: ConfigurationError):
    return JSONResponse(status_code=500, content={"success": False, "error": str(exc)})


# --- Dependencies ---


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """FastAPI dependency to verify the HTTP Bearer token."""
    token = credentials.credentials
    if not validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    return token


# --- API Endpoints ---


@app.post("/api/repository", response_model=OperationResponse)
def repository_operations(
    req: RepositoryRequest = Body(...), token: str = Depends(verify_token)
) -> OperationResponse:
    """Handles single repository creation or deletion requests."""
    manager = create_privilege_manager(req.model_dump(), req.action)
    result = manager.run()

    return OperationResponse(
        success=True,
        data=result,
        message=f"Successfully {req.action}d repository and privileges",
    )


@app.post("/api/repository/batch", response_model=BatchOperationResponse)
def batch_repository_operations(
    batch: BatchRequest = Body(...), token: str = Depends(verify_token)
) -> BatchOperationResponse:
    """Handles batch processing of repository creation or deletion requests."""
    results = []
    errors = []

    for i, req in enumerate(batch.requests):
        try:
            manager = create_privilege_manager(req.model_dump(), req.action)
            result = manager.run()
            results.append(
                {
                    "index": i,
                    "success": True,
                    "data": result,
                    "message": f"Successfully {req.action}d repository and privileges",
                }
            )
        except Exception as e:
            errors.append({"index": i, "success": False, "error": str(e)})
            if batch.fail_fast:
                break

    return BatchOperationResponse(
        success=len(errors) == 0,
        message=f"Batch processing completed. {len(results)}/{len(batch.requests)} requests succeeded",
        processed_count=len(results),
        total_requests=len(batch.requests),
        results=results,
        errors=errors or None,
    )


@app.get("/api/health")
def health_check() -> dict:
    """Provides a simple health check endpoint."""
    return {"success": True, "status": "healthy"}
