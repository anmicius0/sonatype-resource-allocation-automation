"""
Core business logic for Nexus Repository Manager automation.

This module contains all the main business logic including:
- Configuration management
- Nexus and IQ Server API clients
- Repository and privilege management
- Main CLI entry point
"""

import os
import sys
import json
import argparse
import requests
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

from .error_handler import ErrorHandler

# Get the directory where the script/executable is located
if getattr(sys, "frozen", False):
    # If running as a packaged executable
    application_path = os.path.dirname(sys.executable)
else:
    # If running as a Python script - go up one level from nexus_manager to project root
    application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env file from the config directory
env_path = os.path.join(application_path, "config", ".env")
load_dotenv(env_path)


def get_fallback_package_manager_config() -> Dict[str, Any]:
    """Get fallback package manager configuration from environment or defaults."""
    return {
        "apt": {"endpoint": "apt", "proxy_supported": True},
        "docker": {"endpoint": "docker", "proxy_supported": True},
        "maven2": {
            "endpoint": "maven",
            "proxy_supported": True,
            "privilege_format": "maven",
        },
        "npm": {"endpoint": "npm", "proxy_supported": True},
        "nuget": {"endpoint": "nuget", "proxy_supported": True},
        "pypi": {"endpoint": "pypi", "proxy_supported": True},
        "yum": {"endpoint": "yum", "proxy_supported": True},
    }


@dataclass(frozen=True)
class Config:
    """Configuration for Nexus Repository Manager operations."""

    action: str
    nexus_url: str
    nexus_username: str
    nexus_password: str
    nexus_api_path: str
    iqserver_url: str
    iqserver_username: str
    iqserver_password: str
    ldap_username: str
    organization_id: str
    remote_url: str
    extra_roles: List[str]
    repository_name: str
    privilege_name: str
    role_name: str
    package_manager: str

    @classmethod
    def from_env_and_args(cls) -> "Config":
        """Create config from environment variables and command line args."""
        parser = argparse.ArgumentParser()
        parser.add_argument("action", choices=["create", "delete"])
        action = parser.parse_args().action
        return cls._create_from_env(action, require_all_env=True)

    @classmethod
    def from_env_and_action(cls, action: str) -> "Config":
        """Create config from environment variables and provided action (for Flask app)."""
        return cls._create_from_env(action, require_all_env=False)

    @classmethod
    def _create_from_env(cls, action: str, require_all_env: bool = True) -> "Config":
        """Unified config creation from environment variables."""
        # Required system configuration
        required_system_vars = [
            "NEXUS_URL",
            "NEXUS_USERNAME",
            "NEXUS_PASSWORD",
            "IQSERVER_URL",
            "IQSERVER_USERNAME",
            "IQSERVER_PASSWORD",
        ]

        # Required user input (may come from CLI or web form)
        required_user_vars = ["LDAP_USERNAME", "PACKAGE_MANAGER"]

        # Check all required vars when running from CLI
        if require_all_env:
            required_user_vars.extend(required_system_vars)

        # Validate required environment variables
        for var in required_system_vars + required_user_vars:
            if not os.getenv(var):
                raise ValueError(f"Missing environment variable: {var}")

        # Handle shared repository logic
        shared = os.getenv("SHARED", "false").lower() == "true"
        app_id = os.getenv("APP_ID", "")

        if not shared and not app_id:
            raise ValueError("APP_ID is required when not using shared repository")

        # Load remote URL configuration
        pm = os.environ["PACKAGE_MANAGER"]
        remote_url = cls._get_remote_url(pm)

        # Build repository identifiers
        aid = "shared" if shared else app_id
        repo_name = f"{pm}-release-{aid}"

        # Parse extra roles
        extra_roles = [
            r.strip() for r in os.getenv("DEFAULT_ROLES", "").split(",") if r.strip()
        ]

        return cls(
            action=action,
            nexus_url=os.environ["NEXUS_URL"],
            nexus_username=os.environ["NEXUS_USERNAME"],
            nexus_password=os.environ["NEXUS_PASSWORD"],
            nexus_api_path=os.getenv("NEXUS_API_PATH", "/service/rest"),
            iqserver_url=os.environ["IQSERVER_URL"],
            iqserver_username=os.environ["IQSERVER_USERNAME"],
            iqserver_password=os.environ["IQSERVER_PASSWORD"],
            ldap_username=os.environ["LDAP_USERNAME"],
            organization_id=os.getenv("ORGANIZATION_ID", ""),
            remote_url=remote_url,
            extra_roles=extra_roles,
            repository_name=repo_name,
            privilege_name=repo_name,
            role_name=os.environ["LDAP_USERNAME"],
            package_manager=pm,
        )

    @staticmethod
    def _get_remote_url(package_manager: str) -> str:
        """Load remote URL for the given package manager."""
        try:
            config_path = os.path.join(
                application_path, "config", "package_manager_config.json"
            )
            with open(config_path) as f:
                config = json.load(f)
                supported_formats = config.get("supported_formats", {})

            # Try to find the package manager configuration
            pm_config = supported_formats.get(package_manager) or supported_formats.get(
                package_manager.lower()
            )

            if not pm_config:
                raise ValueError(
                    f"No configuration found for package manager: {package_manager}"
                )

            url = pm_config.get("default_url")
            if not url:
                raise ValueError(
                    f"No remote URL configured for package manager: {package_manager}"
                )
            return url
        except FileNotFoundError:
            raise ValueError(
                "Configuration file 'package_manager_config.json' not found"
            )


class NexusClient:
    """Client for interacting with Nexus Repository Manager API."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        api_path: str = "/service/rest",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_path = api_path
        self.s = requests.Session()
        self.s.auth = (username, password)
        self.s.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        self.supported_formats = self._load_package_manager_config()
        self.api_endpoints = self._load_api_endpoints()

    def _load_package_manager_config(self) -> Dict[str, Any]:
        """Load package manager configuration with fallback."""
        try:
            config_path = os.path.join(
                application_path, "config", "package_manager_config.json"
            )
            with open(config_path) as f:
                return json.load(f).get("supported_formats", {})
        except FileNotFoundError:
            return get_fallback_package_manager_config()

    def _load_api_endpoints(self) -> Dict[str, Any]:
        """Load Nexus API endpoint configurations."""
        try:
            config_path = os.path.join(
                application_path, "config", "nexus_api_endpoints.json"
            )
            with open(config_path) as f:
                config = json.load(f)
                return config.get("proxy_repository_endpoints", {})
        except FileNotFoundError:
            # Fallback endpoint mapping
            return {
                pm: {
                    "path": f"/v1/repositories/{pm}/proxy",
                    "required_fields": [
                        "httpClient",
                        "name",
                        "negativeCache",
                        "online",
                        "proxy",
                        "storage",
                    ],
                }
                for pm in self.supported_formats.keys()
            }

    def _req(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """Make API request with basic error handling."""
        url = f"{self.base_url}{self.api_path}{endpoint}"
        try:
            r = self.s.request(method, url, **kwargs)
            if r.status_code != 404:
                r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(
                f"{method} {url} failed: {e.response.status_code} {e.response.text}",
                response=e.response,
            )
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"API {url} failed: {e}")

    @ErrorHandler.handle_operation("repository lookup", return_none_on_error=True)
    def get_repository(self, name: str) -> Optional[Dict[str, Any]]:
        """Get repository by name."""
        r = self._req("GET", f"/v1/repositories/{name}")
        return r.json() if r.ok else None

    @ErrorHandler.handle_operation("repository creation")
    def create_proxy_repository(self, name: str, pm: str, remote_url: str) -> bool:
        """Create a proxy repository with format-specific API configuration."""
        pm_lower = pm.lower()
        format_config = self.supported_formats.get(pm_lower)
        api_config = self.api_endpoints.get(pm_lower)

        if not format_config or not format_config.get("proxy_supported", False):
            raise ValueError(
                f"Package manager '{pm}' does not support proxy repositories"
            )

        if not api_config:
            raise ValueError(
                f"No API endpoint configuration found for package manager: {pm}"
            )

        # Build base configuration
        config = {
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

        # Add format-specific configuration from API endpoints
        format_specific_config = api_config.get("format_specific_config", {})
        if format_specific_config:
            config.update(format_specific_config)

        # Add any default config from package manager config
        default_config = format_config.get("default_config", {})
        if default_config:
            # For package managers that need their config in a specific key
            if pm_lower == "apt":
                config["apt"] = default_config
            elif pm_lower == "maven2":
                config["maven"] = default_config
            elif pm_lower == "npm":
                config["npm"] = default_config
            elif pm_lower == "pypi":
                config["pypi"] = default_config
            elif pm_lower == "nuget":
                config["nugetProxy"] = default_config
            elif pm_lower == "yum":
                config["yumSigning"] = default_config
            else:
                config.update(default_config)

        # Use the specific API path from configuration
        api_path = api_config["path"]
        r = self._req("POST", api_path, json=config)
        return r.status_code == 201

    @ErrorHandler.handle_operation("repository deletion")
    def delete_repository(self, name: str) -> bool:
        """Delete repository by name."""
        r = self._req("DELETE", f"/v1/repositories/{name}")
        return r.status_code in [204, 404]

    @ErrorHandler.handle_operation("privilege lookup", return_none_on_error=True)
    def get_privilege(self, name: str) -> Optional[Dict[str, Any]]:
        """Get privilege by name."""
        r = self._req("GET", f"/v1/security/privileges/{name}")
        return r.json() if r.ok else None

    @ErrorHandler.handle_operation("privilege creation")
    def create_privilege(self, name: str, repo_name: str, pm: str) -> bool:
        """Create privilege for repository."""
        format_config = self.supported_formats.get(pm.lower(), {})
        privilege_format = format_config.get("privilege_format", pm.lower())

        config = {
            "name": name,
            "description": f"All permissions for repository '{repo_name}'",
            "actions": ["BROWSE", "READ", "EDIT", "ADD", "DELETE"],
            "format": privilege_format,
            "repository": repo_name,
        }
        r = self._req("POST", "/v1/security/privileges/repository-view", json=config)
        return r.ok

    @ErrorHandler.handle_operation("privilege deletion")
    def delete_privilege(self, name: str) -> bool:
        """Delete privilege by name."""
        r = self._req("DELETE", f"/v1/security/privileges/{name}")
        return r.status_code in [204, 404]

    @ErrorHandler.handle_operation("role lookup", return_none_on_error=True)
    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        """Get role by name."""
        r = self._req("GET", f"/v1/security/roles/{name}")
        return r.json() if r.ok else None

    @ErrorHandler.handle_operation("role management")
    def create_role(self, name: str, desc: str, privileges: List[str]) -> bool:
        """Create new role with privileges."""
        config = {
            "id": name,
            "name": name,
            "description": desc,
            "privileges": privileges,
            "roles": [],
        }
        r = self._req("POST", "/v1/security/roles", json=config)
        return r.status_code in [200, 201]

    @ErrorHandler.handle_operation("role management")
    def update_role(self, role: Dict[str, Any]) -> bool:
        """Update existing role."""
        r = self._req("PUT", f"/v1/security/roles/{role['id']}", json=role)
        return r.status_code == 204

    @ErrorHandler.handle_operation("role management")
    def delete_role(self, name: str) -> bool:
        """Delete role by name."""
        r = self._req("DELETE", f"/v1/security/roles/{name}")
        return r.status_code in [204, 404]

    @ErrorHandler.handle_operation("user lookup", return_none_on_error=True)
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        r = self._req("GET", "/v1/security/users", params={"userId": user_id})
        if r.ok:
            users = r.json()
            return next((u for u in users if u.get("userId") == user_id), None)
        return None

    @ErrorHandler.handle_operation("user management")
    def update_user(self, user: Dict[str, Any]) -> bool:
        """Update user information."""
        r = self._req("PUT", f"/v1/security/users/{user['userId']}", json=user)
        return r.status_code == 204


class IQServerClient:
    """Client for interacting with IQ Server API."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.auth = (username, password)
        self.s.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def _req(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        """Make API request with basic error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            r = self.s.request(method, url, **kwargs)
            if r.status_code != 404:
                r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            raise requests.exceptions.HTTPError(
                f"{method} {url} failed: {e.response.status_code} {e.response.text}",
                response=e.response,
            )
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"API {url} failed: {e}")

    @ErrorHandler.handle_operation("role lookup", return_none_on_error=True)
    def get_roles(self) -> List[Dict[str, Any]]:
        """Fetch all roles from IQ Server."""
        r = self._req("GET", "/api/v2/roles")
        return r.json().get("roles", []) if r.ok else []

    @ErrorHandler.handle_operation("role lookup", return_none_on_error=True)
    def find_owner_role_id(self) -> Optional[str]:
        """Find the role ID for the 'Owner' role."""
        roles = self.get_roles()
        for role in roles:
            if role.get("name") == "Owner":
                return role.get("id")
        return None

    @ErrorHandler.handle_operation("user role assignment")
    def grant_role_to_user(
        self, internal_owner_id: str, role_id: str, member_name: str
    ) -> bool:
        """Grant a role to a user for the specified organization."""
        endpoint = f"/api/v2/roleMemberships/organization/{internal_owner_id}/role/{role_id}/user/{member_name}"
        r = self._req("PUT", endpoint)
        return r.status_code in [200, 204]

    @ErrorHandler.handle_operation("user role revocation")
    def revoke_role_from_user(
        self, internal_owner_id: str, role_id: str, member_name: str
    ) -> bool:
        """Revoke a role from a user for the specified organization."""
        endpoint = f"/api/v2/roleMemberships/organization/{internal_owner_id}/role/{role_id}/user/{member_name}"
        r = self._req("DELETE", endpoint)
        return r.status_code in [200, 204]


class PrivilegeManager:
    """Main business logic for managing Nexus repositories and privileges."""

    def __init__(self, config: Config):
        self.c = config
        self.n = NexusClient(
            config.nexus_url,
            config.nexus_username,
            config.nexus_password,
            config.nexus_api_path,
        )
        self.iq = IQServerClient(
            config.iqserver_url, config.iqserver_username, config.iqserver_password
        )

    def run(self) -> None:
        """Execute the requested operation."""
        print(
            f"\n🔧 {self.c.action.upper()} Nexus Repository: {self.c.repository_name}"
        )
        print(f"👤 User/Role: {self.c.role_name}")

        if self.c.action == "create":
            self._create_resources()
        else:
            self._delete_resources()
        print("\n✅ Done!")

    def _create_resources(self) -> None:
        """Create all required resources."""
        # Create repository if needed
        print("  ➡️ Checking repository...")
        if not self.n.get_repository(self.c.repository_name):
            print("    🏗️ Creating repository...")
            if not self.n.create_proxy_repository(
                self.c.repository_name, self.c.package_manager, self.c.remote_url
            ):
                raise RuntimeError("Repository creation failed")
        else:
            print("    ✔️ Repository exists")

        # Create privilege if needed
        print("  ➡️ Checking privilege...")
        if not self.n.get_privilege(self.c.privilege_name):
            print("    🏗️ Creating privilege...")
            if not self.n.create_privilege(
                self.c.privilege_name, self.c.repository_name, self.c.package_manager
            ):
                raise RuntimeError("Privilege creation failed")
        else:
            print("    ✔️ Privilege exists")

        self._setup_role_and_user()
        self._setup_iq_server_role()

    def _setup_role_and_user(self) -> None:
        """Setup role and link it to user."""
        print("  ➡️ Setting up role and user...")

        # Ensure role exists and has privilege
        role = self.n.get_role(self.c.role_name)
        if not role:
            print("    🏗️ Creating role...")
            if not self.n.create_role(
                self.c.role_name,
                f"Role for {self.c.ldap_username}",
                [self.c.privilege_name],
            ):
                raise RuntimeError("Role creation failed")
        elif self.c.privilege_name not in role.get("privileges", []):
            print("    🔗 Adding privilege to role...")
            role["privileges"].append(self.c.privilege_name)
            if not self.n.update_role(role):
                raise RuntimeError("Failed to update role")

        # Ensure user has role
        user = self.n.get_user(self.c.ldap_username)
        if not user:
            raise RuntimeError(f"User '{self.c.ldap_username}' not found")

        current_roles = set(user.get("roles", []))
        required_roles = set([self.c.role_name] + self.c.extra_roles)

        if not required_roles.issubset(current_roles):
            print("    🔗 Adding roles to user...")
            user["roles"] = sorted(list(current_roles | required_roles))
            if not self.n.update_user(user):
                raise RuntimeError("Failed to update user")
        else:
            print("    ✔️ User has required roles")

    def _setup_iq_server_role(self) -> None:
        """Setup IQ Server role (optional operation)."""
        if not self.c.organization_id:
            print("    ⚠️ No organization ID configured, skipping IQ Server role")
            return

        try:
            print("  ➡️ Setting up IQ Server role...")
            owner_role_id = self.iq.find_owner_role_id()
            if not owner_role_id:
                print("    ⚠️ Owner role not found in IQ Server")
                return

            if self.iq.grant_role_to_user(
                self.c.organization_id, owner_role_id, self.c.ldap_username
            ):
                print("    ✅ IQ Server role granted")
            else:
                print("    ⚠️ Failed to grant IQ Server role")
        except Exception as e:
            print(f"    ⚠️ IQ Server setup failed: {e}")

    def _delete_resources(self) -> None:
        """Delete all resources."""
        print("  ➡️ Cleaning up...")

        # Cleanup role assignments
        self._cleanup_role()
        self._cleanup_iq_server_role()

        # Delete privilege and repository
        if not self.n.delete_privilege(self.c.privilege_name):
            print("    ⚠️ Privilege deletion failed or already absent")

        if not self.n.delete_repository(self.c.repository_name):
            print("    ⚠️ Repository deletion failed or already absent")

    def _cleanup_role(self) -> None:
        """Cleanup role and user assignments."""
        role = self.n.get_role(self.c.role_name)
        if not role:
            return

        # Remove privilege from role
        privileges = set(role.get("privileges", []))
        if self.c.privilege_name in privileges:
            privileges.remove(self.c.privilege_name)

            if not privileges:  # Role will be empty, delete it
                print("    🗑️ Deleting empty role...")
                user = self.n.get_user(self.c.ldap_username)
                if user and self.c.role_name in user.get("roles", []):
                    user["roles"].remove(self.c.role_name)
                    self.n.update_user(user)
                self.n.delete_role(self.c.role_name)
            else:  # Update role without this privilege
                role["privileges"] = list(privileges)
                self.n.update_role(role)

    def _cleanup_iq_server_role(self) -> None:
        """Cleanup IQ Server role (optional operation)."""
        if not self.c.organization_id:
            return

        try:
            owner_role_id = self.iq.find_owner_role_id()
            if owner_role_id:
                self.iq.revoke_role_from_user(
                    self.c.organization_id, owner_role_id, self.c.ldap_username
                )
        except Exception as e:
            print(f"    ⚠️ IQ Server cleanup failed: {e}")


@ErrorHandler.handle_main_execution
def main() -> None:
    """Main CLI entry point."""
    config = Config.from_env_and_args()
    PrivilegeManager(config).run()


if __name__ == "__main__":
    main()
