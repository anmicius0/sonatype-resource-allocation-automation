# src/create_repo/clients.py
"""
HTTP API client classes for external service interactions.
"""

import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import List, Optional, Dict, Any

from create_repo.common import (
    ConfigurationError,
    ValidationError,
)


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
        logger.debug(f"Initializing APIClient for {base_url}{path_prefix}")
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
        logger.debug("APIClient initialized successfully with retry strategy")

    def _req(
        self, method: str, endpoint: str, raise_for_status: bool = True, **kwargs: Any
    ) -> requests.Response:
        """Makes an API request and optionally handles standard HTTP errors."""
        url = f"{self.base_url}{self.path_prefix}{endpoint}"
        request_body = kwargs.get("json") or kwargs.get("data")
        logger.info(f"HTTP Request: {method} {url} | Body: {request_body}")
        response = self.s.request(method, url, **kwargs)
        response_body = (response.text or "").strip()
        if len(response_body) > 1000:
            response_body = response_body[:1000] + "…"
        logger.info(
            f"HTTP Response: {method} {url} -> {response.status_code} | Body: {response_body}"
        )
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
        """Get repository by name, return None if not found."""
        logger.debug(f"Checking if repository '{name}' exists")
        try:
            r = self._req("GET", f"/v1/repositories/{name}", raise_for_status=False)
            if r.status_code == 404:
                logger.debug(f"Repository '{name}' not found")
                return None
            r.raise_for_status()
            logger.debug(f"Repository '{name}' found")
            return r.json()
        except Exception as e:
            logger.error(f"Failed to get repository {name}: {e}")
            return None

    def create_proxy_repository(self, config) -> None:
        """Creates a proxy repository with format-specific API configuration."""
        logger.debug(
            f"Creating proxy repository '{config.repository_name}' for package manager '{config.package_manager}'"
        )
        logger.debug(f"Remote URL: {config.remote_url}")

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

        logger.debug(f"Using API endpoint: {api_config['path']}")
        repo_config = create_repository_config(
            config.repository_name, config.remote_url, format_config
        )
        repo_config.update(api_config.get("format_specific_config", {}))

        logger.debug(f"Repository configuration: {repo_config}")
        self._req("POST", api_config["path"], json=repo_config)
        logger.debug(f"Repository '{config.repository_name}' created successfully")

    def delete_repository(self, repository_name: str) -> None:
        """Deletes a repository by name."""
        logger.debug(f"Deleting repository '{repository_name}'")
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
        elif r.status_code == 204:
            logger.debug(f"Repository '{repository_name}' deleted successfully")
        elif r.status_code == 404:
            logger.debug(
                f"Repository '{repository_name}' was already deleted or not found"
            )

    def get_privilege(self, name: str) -> Optional[Dict[str, Any]]:
        """Get privilege by name, return None if not found."""
        logger.debug(f"Checking if privilege '{name}' exists")
        try:
            r = self._req(
                "GET", f"/v1/security/privileges/{name}", raise_for_status=False
            )
            if r.status_code == 404:
                logger.debug(f"Privilege '{name}' not found")
                return None
            r.raise_for_status()
            logger.debug(f"Privilege '{name}' found")
            return r.json()
        except Exception as e:
            logger.error(f"Failed to get privilege {name}: {e}")
            return None

    def create_privilege(self, config) -> None:
        """Creates a repository-view privilege."""
        logger.debug(
            f"Creating privilege '{config.privilege_name}' for repository '{config.repository_name}'"
        )

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

        logger.debug(f"Privilege configuration: {privilege_config}")
        self._req(
            "POST", "/v1/security/privileges/repository-view", json=privilege_config
        )
        logger.debug(f"Privilege '{config.privilege_name}' created successfully")

    def delete_privilege(self, privilege_name: str) -> None:
        """Deletes a privilege by name."""
        logger.debug(f"Deleting privilege '{privilege_name}'")
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
        elif r.status_code == 204:
            logger.debug(f"Privilege '{privilege_name}' deleted successfully")
        elif r.status_code == 404:
            logger.debug(
                f"Privilege '{privilege_name}' was already deleted or not found"
            )

    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        """Get role by name, return None if not found."""
        logger.debug(f"Checking if role '{name}' exists")
        try:
            r = self._req("GET", f"/v1/security/roles/{name}", raise_for_status=False)
            if r.status_code == 404:
                logger.debug(f"Role '{name}' not found")
                return None
            r.raise_for_status()
            role = r.json()
            logger.debug(
                f"Role '{name}' found with {len(role.get('privileges', []))} privileges"
            )
            return role
        except Exception as e:
            logger.error(f"Failed to get role {name}: {e}")
            return None

    def create_role(self, config) -> None:
        """Creates a new role with specified privileges."""
        logger.debug(
            f"Creating role '{config.role_name}' for user '{config.ldap_username}'"
        )

        role_config = {
            "id": config.role_name,
            "name": config.role_name,
            "description": f"Role for {config.ldap_username}",
            "privileges": [config.privilege_name],
            "roles": [],
        }

        logger.debug(f"Role configuration: {role_config}")
        self._req("POST", "/v1/security/roles", json=role_config)
        logger.debug(f"Role '{config.role_name}' created successfully")

    def update_role(self, role: Dict[str, Any]) -> None:
        """Updates an existing role's configuration."""
        logger.debug(
            f"Updating role '{role['id']}' with {len(role.get('privileges', []))} privileges"
        )
        logger.debug(f"Role privileges: {role.get('privileges', [])}")
        self._req("PUT", f"/v1/security/roles/{role['id']}", json=role)
        logger.debug(f"Role '{role['id']}' updated successfully")

    def delete_role(self, name: str) -> None:
        """Deletes a role by name."""
        logger.debug(f"Deleting role '{name}'")
        r = self._req("DELETE", f"/v1/security/roles/{name}", raise_for_status=False)
        if r.status_code not in [204, 404]:
            logger.error(f"Failed to delete role '{name}': HTTP {r.status_code}")
            r.raise_for_status()
        elif r.status_code == 204:
            logger.debug(f"Role '{name}' deleted successfully")
        elif r.status_code == 404:
            logger.debug(f"Role '{name}' was already deleted or not found")

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Gets a user by their user ID."""
        logger.debug(f"Looking up user '{user_id}'")
        try:
            r = self._req(
                "GET",
                "/v1/security/users",
                params={"userId": user_id},
                raise_for_status=False,
            )
            if r.status_code == 404:
                logger.debug(f"User '{user_id}' not found")
                return None
            r.raise_for_status()
            users = r.json()
            user = next((u for u in users if u.get("userId") == user_id), None)
            if user:
                logger.debug(
                    f"User '{user_id}' found with {len(user.get('roles', []))} roles: {user.get('roles', [])}"
                )
            else:
                logger.debug(f"User '{user_id}' not found in user list")
            return user
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def update_user(self, user: Dict[str, Any]) -> None:
        """Updates a user's information, typically to add roles."""
        logger.debug(
            f"Updating user '{user['userId']}' with roles: {user.get('roles', [])}"
        )
        self._req("PUT", f"/v1/security/users/{user['userId']}", json=user)
        logger.debug(f"User '{user['userId']}' updated successfully")


class IQServerClient(APIClient):
    """Client for interacting with the Sonatype IQ Server API."""

    def __init__(self, url: str, username: str, password: str):
        super().__init__(url, username, password)

    def get_roles(self) -> List[Dict[str, Any]]:
        """Fetches all roles from IQ Server."""
        logger.debug("Fetching all roles from IQ Server")
        r = self._req("GET", "/api/v2/roles", raise_for_status=False)
        if r.status_code == 404:
            logger.debug("No roles found in IQ Server (404 response)")
            return []
        r.raise_for_status()
        roles = r.json().get("roles", [])
        logger.debug(f"Found {len(roles)} roles in IQ Server")
        return roles

    def find_owner_role_id(self) -> Optional[str]:
        """Finds the ID of the 'Owner' role in IQ Server."""
        logger.debug("Searching for 'Owner' role in IQ Server")
        try:
            roles = self.get_roles()
            for role in roles:
                if role.get("name") == "Owner":
                    role_id = role.get("id")
                    logger.debug(f"Found 'Owner' role with ID: {role_id}")
                    return role_id
            logger.warning("'Owner' role not found in IQ Server")
            return None
        except Exception as e:
            logger.error(f"Failed to find owner role: {e}")
            return None

    def grant_role_to_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        """Grants a role to a user for a specific organization."""
        logger.debug(
            f"Granting role '{role_id}' to user '{ldap_username}' in organization '{organization_id}'"
        )
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        self._req("PUT", endpoint)
        logger.debug(f"Successfully granted role to user '{ldap_username}'")

    def revoke_role_from_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        """Revokes a role from a user for a specific organization."""
        logger.debug(
            f"Revoking role '{role_id}' from user '{ldap_username}' in organization '{organization_id}'"
        )
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        r = self._req("DELETE", endpoint, raise_for_status=False)
        if r.status_code not in [200, 204, 404]:
            logger.error(
                f"Failed to revoke role from user '{ldap_username}': HTTP {r.status_code}"
            )
            r.raise_for_status()
        elif r.status_code in [200, 204]:
            logger.debug(f"Successfully revoked role from user '{ldap_username}'")
        elif r.status_code == 404:
            logger.debug(
                f"Role was already revoked or not found for user '{ldap_username}'"
            )
