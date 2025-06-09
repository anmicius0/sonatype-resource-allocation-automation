"""
HTTP API client classes for external service interactions and core business logic.
"""

import logging
from typing import List, Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from resource_allocation.common import (
    ConfigurationError,
    ValidationError,
)
from resource_allocation.config import OperationConfig


def create_repository_config(
    name: str, remote_url: str, format_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Creates a standard repository configuration dictionary from templates."""
    repo_config = {
        "name": name,
        "online": True,
        "storage": {
            "blobStoreName": "default",
            "strictContentTypeValidation": True,
        },
        "proxy": {
            "remoteUrl": remote_url,
            "contentMaxAge": 1440,
            "metadataMaxAge": 1440,
        },
        "negativeCache": {"enabled": True, "timeToLive": 1440},
        "httpClient": {"blocked": False, "autoBlock": True},
    }

    # Apply format-specific configurations
    repo_config.update(format_config.get("format_specific_config", {}))
    repo_config.update(format_config.get("default_config", {}))

    return repo_config


logger = logging.getLogger(__name__)


class APIClient:
    """Base API client with session management, authentication, and retry logic."""

    def __init__(
        self, base_url: str, username: str, password: str, path_prefix: str = ""
    ):
        """Initializes the API client."""
        self.base_url = base_url.rstrip("/")
        self.path_prefix = path_prefix
        self.s = requests.Session()
        self.s.auth = (username, password)
        self.s.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

        # Configure a retry strategy for transient network or server errors.
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=0.1,
            allowed_methods=[
                "HEAD",
                "GET",
                "PUT",
                "DELETE",
                "OPTIONS",
                "TRACE",
                "POST",
            ],
        )
        adapter = HTTPAdapter(
            pool_connections=10, pool_maxsize=20, max_retries=retry_strategy
        )
        self.s.mount("http://", adapter)
        self.s.mount("https://", adapter)

    def _req(
        self, method: str, endpoint: str, raise_for_status: bool = True, **kwargs: Any
    ) -> requests.Response:
        """Makes an API request and optionally handles standard HTTP errors."""
        url = f"{self.base_url}{self.path_prefix}{endpoint}"
        response = self.s.request(method, url, **kwargs)
        response_body = (response.text or "").strip()
        if len(response_body) > 1000:
            response_body = response_body[:1000] + "…"
        if raise_for_status:
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                logger.error(
                    "%s %s -> %s | %s", method, url, response.status_code, response_body
                )
                raise
        return response


class NexusClient(APIClient):
    """Client for interacting with the Nexus Repository Manager API."""

    def __init__(
        self, url: str, username: str, password: str, supported_formats: Dict[str, Any]
    ):
        super().__init__(url, username, password, "/service/rest")
        self.supported_formats = supported_formats
        if not self.supported_formats:
            raise ConfigurationError("No supported formats provided for Nexus client")

    def get_repository(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._req("GET", f"/v1/repositories/{name}", raise_for_status=False)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Failed to get repository {name}: {e}")
            return None

    def create_proxy_repository(self, config) -> None:
        format_config = self.supported_formats.get(config.package_manager.lower())
        if not format_config or not format_config.get("proxy_supported"):
            logger.error(
                f"Package manager '{config.package_manager}' does not support proxy repositories"
            )
            raise ValidationError(
                f"Package manager '{config.package_manager}' does not support proxy repositories"
            )
        api_config = format_config.get("api_endpoint")
        if not api_config:
            logger.error(
                f"No API endpoint configuration found for package manager: {config.package_manager}"
            )
            raise ValidationError(
                f"No API endpoint configuration found for package manager: {config.package_manager}"
            )
        repo_config = create_repository_config(
            config.repository_name, config.remote_url, format_config
        )
        repo_config.update(api_config.get("format_specific_config", {}))
        self._req("POST", api_config["path"], json=repo_config)

    def delete_repository(self, repository_name: str) -> None:
        r = self._req(
            "DELETE",
            f"/v1/repositories/{repository_name}",
            raise_for_status=False,
        )
        if r.status_code not in [204, 404]:
            logger.error(
                f"Failed to delete repository '{repository_name}': HTTP {r.status_code}"
            )
            r.raise_for_status()

    def get_privilege(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._req(
                "GET", f"/v1/security/privileges/{name}", raise_for_status=False
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Failed to get privilege {name}: {e}")
            return None

    def create_privilege(self, config) -> None:
        format_config = self.supported_formats.get(config.package_manager.lower(), {})
        privilege_format = format_config.get(
            "privilege_format", config.package_manager.lower()
        )
        privilege_config = {
            "name": config.privilege_name,
            "description": f"All permissions for repository '{config.repository_name}'",
            "actions": ["BROWSE", "READ", "EDIT", "ADD", "DELETE"],
            "format": privilege_format,
            "repository": config.repository_name,
        }
        self._req(
            "POST", "/v1/security/privileges/repository-view", json=privilege_config
        )

    def delete_privilege(self, privilege_name: str) -> None:
        r = self._req(
            "DELETE",
            f"/v1/security/privileges/{privilege_name}",
            raise_for_status=False,
        )
        if r.status_code not in [204, 404]:
            logger.error(
                f"Failed to delete privilege '{privilege_name}': HTTP {r.status_code}"
            )
            r.raise_for_status()

    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._req("GET", f"/v1/security/roles/{name}", raise_for_status=False)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            role = r.json()
            return role
        except Exception as e:
            logger.error(f"Failed to get role {name}: {e}")
            return None

    def create_role(self, config) -> None:
        role_config = {
            "id": config.role_name,
            "name": config.role_name,
            "description": f"Role for {config.ldap_username}",
            "privileges": [config.privilege_name],
            "roles": [],
        }
        self._req("POST", "/v1/security/roles", json=role_config)

    def update_role(self, role: Dict[str, Any]) -> None:
        self._req("PUT", f"/v1/security/roles/{role['id']}", json=role)

    def delete_role(self, name: str) -> None:
        r = self._req("DELETE", f"/v1/security/roles/{name}", raise_for_status=False)
        if r.status_code not in [204, 404]:
            logger.error(f"Failed to delete role '{name}': HTTP {r.status_code}")
            r.raise_for_status()

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            r = self._req(
                "GET",
                "/v1/security/users",
                params={"userId": user_id},
                raise_for_status=False,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            users = r.json()
            user = next((u for u in users if u.get("userId") == user_id), None)
            return user
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def update_user(self, user: Dict[str, Any]) -> None:
        self._req("PUT", f"/v1/security/users/{user['userId']}", json=user)


class IQServerClient(APIClient):
    """Client for interacting with the Sonatype IQ Server API."""

    def __init__(self, url: str, username: str, password: str):
        super().__init__(url, username, password)

    def get_roles(self) -> List[Dict[str, Any]]:
        r = self._req("GET", "/api/v2/roles", raise_for_status=False)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        roles = r.json().get("roles", [])
        return roles

    def find_owner_role_id(self) -> Optional[str]:
        try:
            roles = self.get_roles()
            for role in roles:
                if role.get("name") == "Owner":
                    role_id = role.get("id")
                    return role_id
            logger.warning("'Owner' role not found in IQ Server")
            return None
        except Exception as e:
            logger.error(f"Failed to find owner role: {e}")
            return None

    def grant_role_to_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        self._req("PUT", endpoint)

    def revoke_role_from_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        r = self._req("DELETE", endpoint, raise_for_status=False)
        if r.status_code not in [200, 204, 404]:
            logger.error(
                f"Failed to revoke role from user '{ldap_username}': HTTP {r.status_code}"
            )
            r.raise_for_status()


class ResourceCreator:
    """Handles creation of Nexus resources (repositories, privileges, roles)."""

    def __init__(self, config: OperationConfig, nexus: NexusClient):
        self.config = config
        self.nexus = nexus

    def create_repository(self) -> None:
        """Creates a repository if it doesn't exist."""
        if not self.nexus.get_repository(self.config.repository_name):
            logger.info(f"Creating repository: {self.config.repository_name}")
            self.nexus.create_proxy_repository(self.config)
            logger.info(
                f"Repository '{self.config.repository_name}' created successfully"
            )
        else:
            logger.info(
                f"Repository '{self.config.repository_name}' already exists - skipping creation"
            )

    def create_privilege(self) -> None:
        """Creates a privilege if it doesn't exist."""
        if not self.nexus.get_privilege(self.config.privilege_name):
            logger.info(f"Creating privilege: {self.config.privilege_name}")
            self.nexus.create_privilege(self.config)
            logger.info(
                f"Privilege '{self.config.privilege_name}' created successfully"
            )
        else:
            logger.info(
                f"Privilege '{self.config.privilege_name}' already exists - skipping creation"
            )

    def create_or_update_role(self) -> None:
        """Creates a new role or updates existing role with the privilege."""
        role = self.nexus.get_role(self.config.role_name)
        if role is None:
            logger.info(f"Creating new role: {self.config.role_name}")
            self.nexus.create_role(self.config)
            logger.info(f"Role '{self.config.role_name}' created successfully")
        elif self.config.privilege_name not in role.get("privileges", []):
            logger.info(
                f"Adding privilege '{self.config.privilege_name}' to existing role '{self.config.role_name}'"
            )
            role["privileges"].append(self.config.privilege_name)
            self.nexus.update_role(role)
            logger.info(
                f"Privilege added to role '{self.config.role_name}' successfully"
            )
        else:
            logger.info(
                f"Role '{self.config.role_name}' already has required privilege - skipping update"
            )


class UserRoleManager:
    """Handles user role assignments in Nexus."""

    def __init__(self, config: OperationConfig, nexus: NexusClient):
        self.config = config
        self.nexus = nexus

    def assign_roles_to_user(self) -> None:
        """Assigns required roles to the user."""
        user = self.nexus.get_user(self.config.ldap_username)
        if not user:
            logger.error(f"User '{self.config.ldap_username}' not found in Nexus")
            raise ConfigurationError(
                f"User '{self.config.ldap_username}' not found in Nexus."
            )

        current_roles = set(user.get("roles", []))
        required_roles = set([self.config.role_name] + self.config.extra_roles)

        if not required_roles.issubset(current_roles):
            new_roles = sorted(list(current_roles | required_roles))
            logger.info(
                f"Adding required roles to user '{self.config.ldap_username}': {sorted(required_roles - current_roles)}"
            )
            user["roles"] = new_roles
            self.nexus.update_user(user)
            logger.info(f"User roles updated successfully. New role list: {new_roles}")
        else:
            logger.info(
                f"User '{self.config.ldap_username}' already has all required roles - skipping update"
            )

    def remove_role_from_user(self, role_name: str) -> None:
        """Removes a specific role from the user."""
        user = self.nexus.get_user(self.config.ldap_username)
        if user:
            original_roles = user.get("roles", [])
            user["roles"] = [r for r in original_roles if r != role_name]
            self.nexus.update_user(user)
            logger.info(
                f"Removed role '{role_name}' from user '{self.config.ldap_username}'"
            )


class ResourceCleaner:
    """Handles deletion and cleanup of Nexus resources."""

    def __init__(
        self, config: OperationConfig, nexus: NexusClient, user_manager: UserRoleManager
    ):
        self.config = config
        self.nexus = nexus
        self.user_manager = user_manager

    def cleanup_shared_repository(self) -> None:
        """Handles cleanup for shared repositories (only removes privilege from shared role)."""
        logger.info("Shared repository: removing privilege from shared role")
        role = self.nexus.get_role(self.config.role_name)
        if role and self.config.privilege_name in role.get("privileges", []):
            role["privileges"].remove(self.config.privilege_name)
            self.nexus.update_role(role)
            logger.info(
                f"Successfully removed privilege '{self.config.privilege_name}' from shared role"
            )
        else:
            logger.info("Privilege not found in shared role - nothing to remove")

    def cleanup_dedicated_repository(self) -> None:
        """Handles full cleanup for dedicated (non-shared) repositories."""
        role = self.nexus.get_role(self.config.role_name)
        if role:
            privileges = set(role.get("privileges", []))
            if self.config.privilege_name in privileges:
                privileges.remove(self.config.privilege_name)
                if not privileges:
                    logger.info(
                        f"Role '{self.config.role_name}' will be empty after privilege removal - deleting role"
                    )
                    self.user_manager.remove_role_from_user(self.config.role_name)
                    self.nexus.delete_role(self.config.role_name)
                    logger.info(f"Deleted empty role '{self.config.role_name}'")
                else:
                    logger.info(
                        f"Role '{self.config.role_name}' still has other privileges - updating role"
                    )
                    role["privileges"] = list(privileges)
                    self.nexus.update_role(role)
                    logger.info(
                        f"Updated role '{self.config.role_name}' with remaining privileges: {sorted(privileges)}"
                    )
            else:
                logger.info(
                    f"Privilege '{self.config.privilege_name}' not found in role '{self.config.role_name}' - skipping role update"
                )
        else:
            logger.info(
                f"Role '{self.config.role_name}' not found - skipping role cleanup"
            )

        # Delete the privilege and repository for dedicated repos
        self.nexus.delete_privilege(self.config.privilege_name)
        logger.info(f"Successfully deleted privilege '{self.config.privilege_name}'")

        self.nexus.delete_repository(self.config.repository_name)
        logger.info(f"Successfully deleted repository '{self.config.repository_name}'")


class IQServerManager:
    """Handles IQ Server role management."""

    def __init__(self, config: OperationConfig, iq: IQServerClient):
        self.config = config
        self.iq = iq

    def grant_owner_role(self) -> None:
        """Grants Owner role to user in IQ Server organization."""
        if not self.config.organization_id:
            return

        logger.info("Setting up IQ Server permissions")
        owner_role_id = self.iq.find_owner_role_id()
        if owner_role_id:
            self.iq.grant_role_to_user(
                owner_role_id,
                self.config.organization_id,
                self.config.ldap_username,
            )
            logger.info(
                f"Successfully granted 'Owner' role to '{self.config.ldap_username}' in IQ Server organization '{self.config.organization_id}'"
            )
        else:
            logger.warning(
                "Could not find 'Owner' role in IQ Server - skipping IQ permissions"
            )

    def revoke_owner_role(self) -> None:
        """Revokes Owner role from user in IQ Server organization."""
        if not self.config.organization_id:
            return

        logger.info("Revoking IQ Server permissions")
        owner_role_id = self.iq.find_owner_role_id()
        if owner_role_id:
            self.iq.revoke_role_from_user(
                owner_role_id,
                self.config.organization_id,
                self.config.ldap_username,
            )
            logger.info(
                f"Successfully revoked IQ Server 'Owner' role from '{self.config.ldap_username}' in organization '{self.config.organization_id}'"
            )
        else:
            logger.warning(
                "Could not find 'Owner' role in IQ Server - skipping IQ permissions cleanup"
            )


class PrivilegeManager:
    """Orchestrates resource allocation operations using specialized managers."""

    def __init__(self, config: OperationConfig, nexus: NexusClient, iq: IQServerClient):
        self.config = config
        self.nexus = nexus
        self.iq = iq

        # Initialize specialized managers
        self.resource_creator = ResourceCreator(config, nexus)
        self.user_manager = UserRoleManager(config, nexus)
        self.resource_cleaner = ResourceCleaner(config, nexus, self.user_manager)
        self.iq_manager = IQServerManager(config, iq)

    def run(self) -> Dict[str, Any]:
        """Executes the requested operation ('create' or 'delete')."""
        logger.info(
            f"Starting {self.config.action} operation for repository '{self.config.repository_name}'"
        )
        logger.debug(
            f"Operation config - User: {self.config.ldap_username}, Organization: {self.config.organization_id}, Package Manager: {self.config.package_manager}, Role: {self.config.role_name}"
        )

        if self.config.action == "create":
            self._create_resources()
        elif self.config.action == "delete":
            self._delete_resources()
        else:
            logger.error(f"Unknown action: {self.config.action}")
            raise ConfigurationError(f"Unknown action: {self.config.action}")

        logger.info(
            f"{self.config.action.capitalize()} operation completed successfully for '{self.config.repository_name}'"
        )

        return {
            "action": self.config.action,
            "repository_name": self.config.repository_name,
            "ldap_username": self.config.ldap_username,
            "organization_id": self.config.organization_id,
            "package_manager": self.config.package_manager,
        }

    def _create_resources(self) -> None:
        """Creates all required resources using specialized managers."""
        self.resource_creator.create_repository()
        self.resource_creator.create_privilege()
        self.resource_creator.create_or_update_role()
        self.user_manager.assign_roles_to_user()
        self.iq_manager.grant_owner_role()

    def _delete_resources(self) -> None:
        """Deletes or cleans up resources using specialized managers."""
        logger.info(
            f"Starting resource cleanup for repository '{self.config.repository_name}'"
        )

        if self.config.role_name == "repositories.share":
            self.resource_cleaner.cleanup_shared_repository()
        else:
            self.iq_manager.revoke_owner_role()
            self.resource_cleaner.cleanup_dedicated_repository()
