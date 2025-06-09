"""
Pydantic data models for API request and response validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any


class RepositoryRequest(BaseModel):
    action: str = Field(
        ..., pattern="^(create|delete)$", description="The operation to perform."
    )
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


class BatchRequest(BaseModel):
    requests: List[RepositoryRequest] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="A list of repository requests to process.",
    )
    fail_fast: bool = Field(
        True, description="If True, the batch operation stops on the first error."
    )
    max_requests: int = Field(
        50,
        ge=1,
        le=100,
        description="Maximum number of requests allowed in a batch.",
    )


# --- Response Models ---
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
