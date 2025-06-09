"""
FastAPI application with repository management endpoints.
"""

import logging
import os
import uuid
from typing import List, Optional, Any

from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from resource_allocation.clients import NexusClient, IQServerClient, PrivilegeManager
from resource_allocation.common import ValidationError, ConfigurationError, get_app_path
from resource_allocation.config import (
    OrganizationProvider,
    PackageManagerProvider,
    CredentialsProvider,
    ConfigurationFactory,
)

logger = logging.getLogger(__name__)


# --- Pydantic Models ---


class RepositoryRequest(BaseModel):
    organization_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The name of the organization.",
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
app = FastAPI()
security = HTTPBearer()

# Initialize the configuration providers
app_path = get_app_path()
config_dir = app_path / "config"

# Create provider instances following dependency injection pattern
org_provider = OrganizationProvider(config_dir)
pm_provider = PackageManagerProvider(config_dir)
creds_provider = CredentialsProvider()
config_factory = ConfigurationFactory(org_provider, pm_provider, creds_provider)

logger.info("Configuration providers initialized")


def create_clients():
    """Factory function to create Nexus and IQ Server clients."""
    nexus_creds = creds_provider.get_nexus_credentials()
    iq_creds = creds_provider.get_iqserver_credentials()
    package_config = pm_provider.get_config()

    nexus_client = NexusClient(
        nexus_creds.url,
        nexus_creds.username,
        nexus_creds.password,
        package_config.get("supported_formats", {}),
    )

    iq_client = IQServerClient(iq_creds.url, iq_creds.username, iq_creds.password)

    return nexus_client, iq_client


def create_privilege_manager(data: dict, action: str) -> PrivilegeManager:
    """Creates a PrivilegeManager instance with the given data and action."""
    nexus_client, iq_client = create_clients()
    operation_config = config_factory.create_operation_config(data, action)

    return PrivilegeManager(operation_config, nexus_client, iq_client)


def validate_token(token: str) -> bool:
    """Validates an API token against the one in the environment."""
    return token == os.getenv("API_TOKEN")


def _process_batch_requests(batch: BatchRepositoryRequest, action: str, batch_id: str):
    """Process a batch of repository requests."""
    action_word = "creation" if action == "create" else "deletion"
    logger.info(
        f"[{batch_id}] Starting batch repository {action_word} for {len(batch.requests)} requests"
    )

    results, errors = [], []

    for i, req in enumerate(batch.requests):
        try:
            manager = create_privilege_manager(req.model_dump(), action)
            data = manager.run()
            logger.info(
                f"[{batch_id}:{i + 1}] Successfully completed repository {action_word} for request {i + 1}"
            )

            results.append(
                {
                    "index": i,
                    "success": True,
                    "data": data,
                    "message": f"Successfully {action_word} repository and privileges",
                }
            )
        except Exception as e:
            logger.error(
                f"[{batch_id}:{i + 1}] Failed to process {action_word} request {i + 1}: {str(e)}"
            )
            error_detail = {
                "index": i,
                "success": False,
                "error": str(e),
                "request": req.model_dump(),
            }
            errors.append(error_detail)
            if batch.fail_fast:
                logger.warning(
                    f"[{batch_id}] Stopping batch operation due to fail_fast=True after error in request {i + 1}"
                )
                break

    success_count = len(results)
    total_count = len(batch.requests)
    logger.info(
        f"[{batch_id}] Batch repository {action_word} completed: {success_count}/{total_count} successful, {len(errors)} errors"
    )

    return results, errors


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
@app.post("/api/repositories", response_model=BatchOperationResponse)
def sonatype_resource_allocation_automation6(
    batch: BatchRepositoryRequest = Body(...), token: str = Depends(verify_token)
):
    """Create one or more repositories and their associated privileges."""
    batch_id = str(uuid.uuid4())[:8]
    results, errors = _process_batch_requests(batch, "create", batch_id)

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
    batch_id = str(uuid.uuid4())[:8]  # Generate a short unique ID for the batch
    results, errors = _process_batch_requests(batch, "delete", batch_id)

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
