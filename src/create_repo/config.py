"""
Application configuration management and organizational data handling.
"""

import logging
import os
from typing import Any, List, Dict
from dataclasses import dataclass
from pathlib import Path

from create_repo.common import (
    load_json_file,
    parse_csv,
    get_resource_path,
    ValidationError,
    ConfigurationError,
)

logger = logging.getLogger(__name__)


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


class AppConfigService:
    """Centralized configuration service for the application."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._organizations = None
        self._package_manager_config = None

    def _load_organizations(self) -> List[Dict[str, Any]]:
        """Loads organizations configuration."""
        if self._organizations is None:
            debug = os.getenv("DEBUG", "false").lower() == "true"
            org_file = "organisations-debug.json" if debug else "organisations.json"
            self._organizations = (
                load_json_file(str(get_resource_path(self.config_dir / org_file))) or []
            )
        return self._organizations

    def _load_package_manager_config(self) -> Dict[str, Any]:
        """Loads package manager configuration."""
        if self._package_manager_config is None:
            self._package_manager_config = load_json_file(
                str(get_resource_path(self.config_dir / "package_manager.json"))
            )
            if not self._package_manager_config:
                raise ConfigurationError("Package manager configuration not found")
        return self._package_manager_config

    def find_organization_by_name(self, chinese_name: str) -> Dict[str, Any]:
        """Finds an organization by its Chinese name."""
        organizations = self._load_organizations()
        for org in organizations:
            if org.get("chineseName") == chinese_name:
                return org
        raise ValidationError(f"Organization '{chinese_name}' not found")

    def get_package_manager_config(self) -> Dict[str, Any]:
        """Gets the package manager configuration."""
        return self._load_package_manager_config()

    def get_remote_url_for_package_manager(self, package_manager: str) -> str:
        """Gets the default remote proxy URL for a given package manager."""
        config = self.get_package_manager_config()
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
            raise ConfigurationError(f"Missing configuration: {', '.join(missing)}")

        return values

    def get_nexus_credentials(self) -> NexusCredentials:
        """Gets Nexus credentials from environment."""
        var_names = ["NEXUS_URL", "NEXUS_USERNAME", "NEXUS_PASSWORD"]
        url, username, password = self._get_required_env_vars(var_names)
        return NexusCredentials(url=url, username=username, password=password)

    def get_iqserver_credentials(self) -> IQServerCredentials:
        """Gets IQ Server credentials from environment."""
        var_names = ["IQSERVER_URL", "IQSERVER_USERNAME", "IQSERVER_PASSWORD"]
        url, username, password = self._get_required_env_vars(var_names)
        return IQServerCredentials(url=url, username=username, password=password)

    def create_operation_config(
        self, data: Dict[str, Any], action: str
    ) -> OperationConfig:
        """Create operation configuration from API request data."""
        # Validate logic for shared vs. application-specific repositories
        shared = data.get("shared", False)
        app_id = data.get("app_id", "")
        if not shared and not app_id:
            raise ValidationError("app_id is required for non-shared repositories")

        # Load organization details
        org = self.find_organization_by_name(data["organization_name_chinese"])

        # Generate resource names
        pm_name = data["package_manager"]
        repo_name = self._generate_repository_name(pm_name, shared, app_id)

        return OperationConfig(
            action=action,
            ldap_username=data["ldap_username"],
            organization_id=org["id"],
            remote_url=self.get_remote_url_for_package_manager(pm_name),
            extra_roles=parse_csv(os.getenv("EXTRA_ROLE", ""), default=[]),
            repository_name=repo_name,
            privilege_name=repo_name,
            role_name="repositories.share" if shared else data["ldap_username"],
            package_manager=pm_name,
        )

    def _generate_repository_name(
        self, package_manager: str, shared: bool, app_id: str
    ) -> str:
        """Generate standardized repository name."""
        suffix = "shared" if shared else app_id
        return f"{package_manager}-release-{suffix}".lower()
