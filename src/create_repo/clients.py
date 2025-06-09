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
        """Creates a proxy repository with format-specific API configuration."""
        format_config = self.supported_formats.get(config.package_manager.lower())

        if not format_config or not format_config.get("proxy_supported"):
            raise ValidationError(
                f"Package manager '{config.package_manager}' does not support proxy repositories"
            )

        api_config = format_config.get("api_endpoint")
        if not api_config:
            raise ValidationError(
                f"No API endpoint configuration found for package manager: {config.package_manager}"
            )

        repo_config = create_repository_config(
            config.repository_name, config.remote_url, format_config
        )
        repo_config.update(api_config.get("format_specific_config", {}))

        self._req("POST", api_config["path"], json=repo_config)

    def delete_repository(self, repository_name: str) -> None:
        """Deletes a repository by name."""
        r = self._req(
            "DELETE",
            f"/v1/repositories/{repository_name}",
            raise_for_status=False,
        )
        if r.status_code not in [204, 404]:
            r.raise_for_status()

    def get_privilege(self, name: str) -> Optional[Dict[str, Any]]:
        """Get privilege by name, return None if not found."""
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
        """Creates a repository-view privilege."""
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
        """Deletes a privilege by name."""
        r = self._req(
            "DELETE",
            f"/v1/security/privileges/{privilege_name}",
            raise_for_status=False,
        )
        if r.status_code not in [204, 404]:
            r.raise_for_status()

    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        """Get role by name, return None if not found."""
        try:
            r = self._req("GET", f"/v1/security/roles/{name}", raise_for_status=False)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Failed to get role {name}: {e}")
            return None

    def create_role(self, config) -> None:
        """Creates a new role with specified privileges."""
        role_config = {
            "id": config.role_name,
            "name": config.role_name,
            "description": f"Role for {config.ldap_username}",
            "privileges": [config.privilege_name],
            "roles": [],
        }
        self._req("POST", "/v1/security/roles", json=role_config)

    def update_role(self, role: Dict[str, Any]) -> None:
        """Updates an existing role's configuration."""
        self._req("PUT", f"/v1/security/roles/{role['id']}", json=role)

    def delete_role(self, name: str) -> None:
        """Deletes a role by name."""
        r = self._req("DELETE", f"/v1/security/roles/{name}", raise_for_status=False)
        if r.status_code not in [204, 404]:
            r.raise_for_status()

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Gets a user by their user ID."""
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
            return next((u for u in users if u.get("userId") == user_id), None)
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def update_user(self, user: Dict[str, Any]) -> None:
        """Updates a user's information, typically to add roles."""
        self._req("PUT", f"/v1/security/users/{user['userId']}", json=user)


class IQServerClient(APIClient):
    """Client for interacting with the Sonatype IQ Server API."""

    def __init__(self, url: str, username: str, password: str):
        super().__init__(url, username, password)

    def get_roles(self) -> List[Dict[str, Any]]:
        """Fetches all roles from IQ Server."""
        r = self._req("GET", "/api/v2/roles", raise_for_status=False)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("roles", [])

    def find_owner_role_id(self) -> Optional[str]:
        """Finds the ID of the 'Owner' role in IQ Server."""
        try:
            roles = self.get_roles()
            for role in roles:
                if role.get("name") == "Owner":
                    return role.get("id")
            return None
        except Exception as e:
            logger.error(f"Failed to find owner role: {e}")
            return None

    def grant_role_to_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        """Grants a role to a user for a specific organization."""
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        self._req("PUT", endpoint)

    def revoke_role_from_user(
        self, role_id: str, organization_id: str, ldap_username: str
    ) -> None:
        """Revokes a role from a user for a specific organization."""
        endpoint = f"/api/v2/roleMemberships/organization/{organization_id}/role/{role_id}/user/{ldap_username}"
        r = self._req("DELETE", endpoint, raise_for_status=False)
        if r.status_code not in [200, 204, 404]:
            r.raise_for_status()
