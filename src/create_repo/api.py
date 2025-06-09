"""
FastAPI application with repository management endpoints.
"""

import os
import logging
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from create_repo.core import PrivilegeManager
from create_repo.clients import NexusClient, IQServerClient
from create_repo.config import AppConfigService
from create_repo.common import get_application_path
from create_repo.common import ValidationError, ConfigurationError

logger = logging.getLogger(__name__)


# --- Pydantic Models ---


class RepositoryRequest(BaseModel):
    organization_name_chinese: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The Chinese name of the organization.",
    )
    ldap_username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="The LDAP username of the requester.",
    )
    package_manager: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="The package manager format (e.g., 'maven2', 'npm').",
    )
    shared: bool = Field(
        ..., description="Whether the repository is shared among multiple users/apps."
    )
    app_id: Optional[str] = Field(
        None,
        max_length=50,
        description="A unique application ID, required for non-shared repositories.",
    )


class BatchRepositoryRequest(BaseModel):
    requests: List[RepositoryRequest] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="A list of repository requests to process.",
    )
    fail_fast: bool = Field(
        True, description="If True, the batch operation stops on the first error."
    )


class OperationResponse(BaseModel):
    """The response model for a single repository operation."""

    success: bool
    data: Any
    message: str


class BatchOperationResponse(BaseModel):
    """The response model for a batch repository operation."""

    success: bool
    message: str
    processed_count: int
    total_requests: int
    results: List[Any]
    errors: Optional[List[Any]]


# --- Application Setup ---

app = FastAPI(
    title="Nexus Repository and Privilege Manager API",
    description="An API to automatically create and manage Nexus repositories and associated privileges.",
    version="1.0.0",
)
security = HTTPBearer()

# Initialize the configuration service once at startup
app_path = get_application_path()
config_dir = app_path / "config"
config_service = AppConfigService(config_dir)
logger.info("Configuration service initialized")
logger.debug(f"Configuration directory: {config_dir.absolute()}")


def create_clients():
    """Factory function to create Nexus and IQ Server clients."""
    logger.debug("Creating Nexus and IQ Server clients")
    nexus_creds = config_service.get_nexus_credentials()
    iq_creds = config_service.get_iqserver_credentials()
    package_config = config_service.get_package_manager_config()

    logger.debug(f"Initializing Nexus client for URL: {nexus_creds.url}")
    nexus_client = NexusClient(
        nexus_creds.url,
        nexus_creds.username,
        nexus_creds.password,
        package_config.get("supported_formats", {}),
    )

    logger.debug(f"Initializing IQ Server client for URL: {iq_creds.url}")
    iq_client = IQServerClient(iq_creds.url, iq_creds.username, iq_creds.password)

    logger.debug("Clients successfully created")
    return nexus_client, iq_client


def create_privilege_manager(data: dict, action: str) -> PrivilegeManager:
    """Creates a PrivilegeManager instance with the given data and action."""
    logger.debug(f"Creating PrivilegeManager for action: {action}")
    logger.debug(f"Request data: {data}")

    nexus_client, iq_client = create_clients()
    operation_config = config_service.create_operation_config(data, action)

    logger.debug(
        f"Operation config created - Repository: {operation_config.repository_name}, "
        f"Role: {operation_config.role_name}, User: {operation_config.ldap_username}"
    )

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


# --- API Endpoints ---


@app.post("/api/repositories", response_model=BatchOperationResponse)
def create_repositories(
    batch: BatchRepositoryRequest = Body(...), token: str = Depends(verify_token)
):
    """Create one or more repositories and their associated privileges."""
    logger.info(
        f"Starting batch repository creation for {len(batch.requests)} requests"
    )
    logger.debug(f"Batch settings - fail_fast: {batch.fail_fast}")

    results, errors = [], []

    for i, req in enumerate(batch.requests):
        logger.debug(
            f"Processing request {i + 1}/{len(batch.requests)}: "
            f"org={req.organization_name_chinese}, "
            f"user={req.ldap_username}, "
            f"package_manager={req.package_manager}, "
            f"shared={req.shared}, "
            f"app_id={req.app_id}"
        )

        try:
            manager = create_privilege_manager(req.model_dump(), "create")
            logger.debug(f"Starting repository creation for request {i + 1}")
            data = manager.run()
            logger.info(
                f"Successfully completed repository creation for request {i + 1}"
            )

            results.append(
                {
                    "index": i,
                    "success": True,
                    "data": data,
                    "message": "Successfully created repository and privileges",
                }
            )
        except Exception as e:
            logger.error(f"Failed to process request {i + 1}: {str(e)}")
            error_detail = {
                "index": i,
                "success": False,
                "error": str(e),
                "request": req.model_dump(),
            }
            errors.append(error_detail)
            if batch.fail_fast:
                logger.warning(
                    f"Stopping batch operation due to fail_fast=True after error in request {i + 1}"
                )
                break

    success_count = len(results)
    total_count = len(batch.requests)
    logger.info(
        f"Batch repository creation completed: {success_count}/{total_count} successful, {len(errors)} errors"
    )

    return BatchOperationResponse(
        success=len(errors) == 0,
        message=f"Processed {len(results)} of {len(batch.requests)} requests successfully",
        processed_count=len(results),
        total_requests=len(batch.requests),
        results=results,
        errors=errors if errors else None,
    )


@app.delete("/api/repositories", response_model=BatchOperationResponse)
def delete_repositories(
    batch: BatchRepositoryRequest = Body(...), token: str = Depends(verify_token)
):
    """Delete one or more repositories and their associated privileges."""
    logger.info(
        f"Starting batch repository deletion for {len(batch.requests)} requests"
    )
    logger.debug(f"Batch settings - fail_fast: {batch.fail_fast}")

    results, errors = [], []

    for i, req in enumerate(batch.requests):
        logger.debug(
            f"Processing deletion request {i + 1}/{len(batch.requests)}: "
            f"org={req.organization_name_chinese}, "
            f"user={req.ldap_username}, "
            f"package_manager={req.package_manager}, "
            f"shared={req.shared}, "
            f"app_id={req.app_id}"
        )

        try:
            manager = create_privilege_manager(req.model_dump(), "delete")
            logger.debug(f"Starting repository deletion for request {i + 1}")
            data = manager.run()
            logger.info(
                f"Successfully completed repository deletion for request {i + 1}"
            )

            results.append(
                {
                    "index": i,
                    "success": True,
                    "data": data,
                    "message": "Successfully deleted repository and privileges",
                }
            )
        except Exception as e:
            logger.error(f"Failed to process deletion request {i + 1}: {str(e)}")
            error_detail = {
                "index": i,
                "success": False,
                "error": str(e),
                "request": req.model_dump(),
            }
            errors.append(error_detail)
            if batch.fail_fast:
                logger.warning(
                    f"Stopping batch deletion due to fail_fast=True after error in request {i + 1}"
                )
                break

    success_count = len(results)
    total_count = len(batch.requests)
    logger.info(
        f"Batch repository deletion completed: {success_count}/{total_count} successful, {len(errors)} errors"
    )

    return BatchOperationResponse(
        success=len(errors) == 0,
        message=f"Processed {len(results)} of {len(batch.requests)} requests successfully",
        processed_count=len(results),
        total_requests=len(batch.requests),
        results=results,
        errors=errors if errors else None,
    )


@app.get("/api/health")
def health_check() -> dict:
    """Provides a simple health check endpoint."""
    return {"success": True, "status": "healthy"}
