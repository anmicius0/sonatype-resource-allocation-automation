"""
Application configuration management following SOLID principles.

This module consolidates all configuration loading and verification into specialized classes:
- OrganizationProvider: Manages organizational data
- PackageManagerProvider: Manages package manager configurations
- CredentialsProvider: Manages external service credentials
- ConfigurationFactory: Creates operation configurations
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Dict, Optional

from resource_allocation.common import (
    load_json_file,
    parse_csv,
    get_resource_path,
    ValidationError,
    ConfigurationError,
)

logger = logging.getLogger(__name__)


# --- Data Classes ---


@dataclass(frozen=True)
class NexusCredentials:
    """Credentials for Nexus Repository Manager."""

    url: str
    username: str
    password: str


@dataclass(frozen=True)
class IQServerCredentials:
    """Credentials for Sonatype IQ Server."""

    url: str
    username: str
    password: str


@dataclass(frozen=True)
class OperationConfig:
    """Configuration for a specific repository operation."""

    action: str
    ldap_username: str
    organization_id: str
    remote_url: str
    extra_roles: List[str]
    repository_name: str
    privilege_name: str
    role_name: str
    package_manager: str


# --- Configuration Providers ---


class OrganizationProvider:
    """Manages organizational data loading and lookup operations."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._organizations: Optional[List[Dict[str, Any]]] = None

    def _load_organizations(self) -> List[Dict[str, Any]]:
        """Loads organizations configuration with fallback strategy."""
        if self._organizations is None:
            org_file = "organizations.json"
            paths_to_try = [
                (self.config_dir / org_file).resolve(),
                get_resource_path(f"config/{org_file}").resolve(),
            ]

            data = None
            for p in paths_to_try:
                logger.info(f"Attempting to load organizations from: {p}")
                if p.exists():
                    data = load_json_file(str(p))
                    break

            if data is None:
                logger.warning("No organizations configuration found; using empty list")
                self._organizations = []
            elif isinstance(data, list):
                self._organizations = data
                logger.info(f"Loaded {len(self._organizations)} organizations")
            else:
                raise ConfigurationError("Organizations configuration must be a list")

        return self._organizations

    def find_organization_by_name(self, name: str) -> Dict[str, Any]:
        """Finds an organization by its name."""
        organizations = self._load_organizations()

        for org in organizations:
            if org.get("name") == name:
                return org

        logger.warning(f"Organization '{name}' not found in configuration")
        raise ValidationError(f"Organization '{name}' not found")

    def get_organizations(self) -> List[Dict[str, Any]]:
        """Gets all organizations."""
        return self._load_organizations()

    def validate_organization_exists(self, name: str) -> bool:
        """Validates if an organization exists."""
        try:
            self.find_organization_by_name(name)
            return True
        except ValidationError:
            return False

    def get_organization_id(self, name: str) -> str:
        """Gets the organization ID for a given name."""
        org = self.find_organization_by_name(name)
        return org["id"]


class PackageManagerProvider:
    """Manages package manager configurations and operations.

    Follows Single Responsibility Principle by only handling package manager operations.
    """

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._config: Optional[Dict[str, Any]] = None

    def _load_config(self) -> Dict[str, Any]:
        """Loads package manager configuration with fallback strategy."""
        if self._config is None:
            external_path = (self.config_dir / "package_manager.json").resolve()
            bundled_path = get_resource_path("config/package_manager.json").resolve()

            logger.info(
                f"Attempting to load package manager config from: {external_path}"
            )
            cfg = None

            # Try external first, then bundled
            if external_path.exists():
                cfg = load_json_file(str(external_path))
            elif bundled_path.exists():
                logger.info(
                    f"Using bundled package manager config from: {bundled_path}"
                )
                cfg = load_json_file(str(bundled_path))

            if not cfg:
                raise ConfigurationError("Package manager configuration not found")

            self._config = cfg

        return self._config

    def get_config(self) -> Dict[str, Any]:
        """Gets the full package manager configuration."""
        return self._load_config()

    def get_remote_url(self, package_manager: str) -> str:
        """Gets the default remote proxy URL for a given package manager."""
        config = self.get_config()
        supported_formats = config.get("supported_formats", {})
        pm_config = supported_formats.get(package_manager.lower())

        if not pm_config:
            raise ConfigurationError(
                f"Package manager '{package_manager}' is not supported"
            )

        remote_url = pm_config.get("default_url")
        if not remote_url:
            raise ConfigurationError(
                f"No remote URL configured for package manager: {package_manager}"
            )

        return remote_url

    def is_supported(self, package_manager: str) -> bool:
        """Checks if a package manager is supported."""
        config = self.get_config()
        supported_formats = config.get("supported_formats", {})
        return package_manager.lower() in supported_formats

    def get_supported_formats(self) -> List[str]:
        """Gets list of all supported package managers."""
        config = self.get_config()
        supported_formats = config.get("supported_formats", {})
        return list(supported_formats.keys())

    def validate_package_manager(self, package_manager: str) -> None:
        """Validates that a package manager is supported."""
        if not self.is_supported(package_manager):
            supported = self.get_supported_formats()
            raise ValidationError(
                f"Package manager '{package_manager}' is not supported. "
                f"Supported formats: {', '.join(supported)}"
            )

    def get_format_config(self, package_manager: str) -> Dict[str, Any]:
        """Gets the full configuration for a specific package manager format."""
        config = self.get_config()
        supported_formats = config.get("supported_formats", {})
        pm_config = supported_formats.get(package_manager.lower())

        if not pm_config:
            raise ConfigurationError(
                f"Package manager '{package_manager}' is not supported"
            )

        return pm_config

    def generate_repository_name(
        self, package_manager: str, shared: bool, app_id: str
    ) -> str:
        """Generate standardized repository name."""
        self.validate_package_manager(package_manager)

        suffix = "shared" if shared else app_id
        repo_name = f"{package_manager}-release-{suffix}".lower()
        return repo_name


class CredentialsProvider:
    """Manages external service credentials from environment variables.

    Follows Single Responsibility Principle by only handling credential operations.
    """

    def _get_required_env_vars(self, var_names: List[str]) -> List[str]:
        """Gets required environment variables, raising an error if any are missing."""
        values = []
        missing = []

        for var in var_names:
            value = os.getenv(var)
            if not value:
                missing.append(var)
            values.append(value)

        if missing:
            raise ConfigurationError(
                f"Missing environment variables: {', '.join(missing)}"
            )

        return values

    def get_nexus_credentials(self) -> NexusCredentials:
        """Gets Nexus credentials from environment variables."""
        var_names = ["NEXUS_URL", "NEXUS_USERNAME", "NEXUS_PASSWORD"]
        url, username, password = self._get_required_env_vars(var_names)
        return NexusCredentials(url=url, username=username, password=password)

    def get_iqserver_credentials(self) -> IQServerCredentials:
        """Gets IQ Server credentials from environment variables."""
        var_names = ["IQSERVER_URL", "IQSERVER_USERNAME", "IQSERVER_PASSWORD"]
        url, username, password = self._get_required_env_vars(var_names)
        return IQServerCredentials(url=url, username=username, password=password)

    def get_extra_roles(self) -> List[str]:
        """Gets extra roles from environment variables."""
        return parse_csv(os.getenv("EXTRA_ROLE", ""), default=[])


class ConfigurationFactory:
    """Factory for creating operation configurations.

    Follows Dependency Inversion Principle by depending on abstractions.
    Follows Open/Closed Principle by being extensible for new operation types.
    """

    def __init__(
        self,
        org_provider: OrganizationProvider,
        pm_provider: PackageManagerProvider,
        creds_provider: CredentialsProvider,
    ):
        self.org_provider = org_provider
        self.pm_provider = pm_provider
        self.creds_provider = creds_provider

    def create_operation_config(
        self, data: Dict[str, Any], action: str
    ) -> OperationConfig:
        """Creates operation configuration from API request data."""
        # Validate shared vs. application-specific logic
        shared = data.get("shared", False)
        app_id = data.get("app_id", "")

        if not shared and not app_id:
            raise ValidationError("app_id is required for non-shared repositories")

        # Validate and get configurations
        pm_name = data["package_manager"]
        self.pm_provider.validate_package_manager(pm_name)

        org = self.org_provider.find_organization_by_name(data["organization_name"])
        repo_name = self.pm_provider.generate_repository_name(pm_name, shared, app_id)
        remote_url = self.pm_provider.get_remote_url(pm_name)
        extra_roles = self.creds_provider.get_extra_roles()

        # Determine role name based on repository type
        role_name = "repositories.share" if shared else data["ldap_username"]

        return OperationConfig(
            action=action,
            ldap_username=data["ldap_username"],
            organization_id=org["id"],
            remote_url=remote_url,
            extra_roles=extra_roles,
            repository_name=repo_name,
            privilege_name=repo_name,
            role_name=role_name,
            package_manager=pm_name,
        )
