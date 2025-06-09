"""
Core business logic for Nexus repository and privilege management.
"""

import logging
from typing import Dict, Any

from create_repo.clients import NexusClient, IQServerClient
from create_repo.app_config import OperationConfig
from create_repo.app_config import ConfigurationError

logger = logging.getLogger(__name__)


class PrivilegeManager:
    """Orchestrates the creation and deletion of Nexus and IQ Server resources."""

    def __init__(self, config: OperationConfig, nexus: NexusClient, iq: IQServerClient):
        self.config = config
        self.nexus = nexus
        self.iq = iq

    def run(self) -> Dict[str, Any]:
        """Executes the requested operation ('create' or 'delete')."""
        logger.info(f"Starting {self.config.action} for {self.config.repository_name}")

        if self.config.action == "create":
            self._create_resources()
        elif self.config.action == "delete":
            self._delete_resources()
        else:
            raise ConfigurationError(f"Unknown action: {self.config.action}")

        logger.info("Operation completed successfully")

        return {
            "action": self.config.action,
            "repository_name": self.config.repository_name,
            "ldap_username": self.config.ldap_username,
            "organization_id": self.config.organization_id,
            "package_manager": self.config.package_manager,
        }

    def _create_resources(self) -> None:
        """Creates all required resources in Nexus and IQ Server."""
        # 1. Create repository if it doesn't exist
        if not self.nexus.get_repository(self.config.repository_name):
            logger.info(f"Creating repository: {self.config.repository_name}")
            self.nexus.create_proxy_repository(self.config)
        else:
            logger.info(f"Repository '{self.config.repository_name}' already exists.")

        # 2. Create privilege if it doesn't exist
        if not self.nexus.get_privilege(self.config.privilege_name):
            logger.info(f"Creating privilege: {self.config.privilege_name}")
            self.nexus.create_privilege(self.config)
        else:
            logger.info(f"Privilege '{self.config.privilege_name}' already exists.")

        # 3. Create or update role
        role = self.nexus.get_role(self.config.role_name)
        if role is None:
            logger.info("Creating new role.")
            self.nexus.create_role(self.config)
        elif self.config.privilege_name not in role.get("privileges", []):
            logger.info("Adding privilege to existing role.")
            role["privileges"].append(self.config.privilege_name)
            self.nexus.update_role(role)

        # 4. Update user roles
        user = self.nexus.get_user(self.config.ldap_username)
        if not user:
            raise ConfigurationError(
                f"User '{self.config.ldap_username}' not found in Nexus."
            )

        current_roles = set(user.get("roles", []))
        required_roles = set([self.config.role_name] + self.config.extra_roles)

        if not required_roles.issubset(current_roles):
            logger.info("Adding required roles to user.")
            user["roles"] = sorted(list(current_roles | required_roles))
            self.nexus.update_user(user)
        else:
            logger.info("User already has all required roles.")

        # 5. IQ Server setup (if organization_id provided)
        if self.config.organization_id:
            logger.info("Setting up IQ Server permissions.")
            owner_role_id = self.iq.find_owner_role_id()
            if owner_role_id:
                self.iq.grant_role_to_user(
                    owner_role_id,
                    self.config.organization_id,
                    self.config.ldap_username,
                )
                logger.info("Successfully granted 'Owner' role in IQ Server.")
            else:
                logger.warning("Could not find 'Owner' role in IQ Server.")

    def _delete_resources(self) -> None:
        """Deletes or cleans up resources based on repository type."""
        logger.info("Starting resource cleanup process.")

        # For shared repositories, only remove privilege from shared role
        if self.config.role_name == "repositories.share":
            logger.info("Shared repository: removing privilege from shared role.")
            role = self.nexus.get_role(self.config.role_name)
            if role and self.config.privilege_name in role.get("privileges", []):
                role["privileges"].remove(self.config.privilege_name)
                self.nexus.update_role(role)
                logger.info("Successfully removed privilege from shared role.")
            return

        # For non-shared repositories, perform full cleanup
        # 1. Clean up role
        role = self.nexus.get_role(self.config.role_name)
        if role:
            privileges = set(role.get("privileges", []))
            if self.config.privilege_name in privileges:
                privileges.remove(self.config.privilege_name)
                if not privileges:
                    # Remove role from user first, then delete empty role
                    user = self.nexus.get_user(self.config.ldap_username)
                    if user:
                        user["roles"] = [
                            r
                            for r in user.get("roles", [])
                            if r != self.config.role_name
                        ]
                        self.nexus.update_user(user)
                    self.nexus.delete_role(self.config.role_name)
                else:
                    role["privileges"] = list(privileges)
                    self.nexus.update_role(role)

        # 2. IQ Server cleanup
        if self.config.organization_id:
            logger.info("Revoking IQ Server permissions.")
            owner_role_id = self.iq.find_owner_role_id()
            if owner_role_id:
                self.iq.revoke_role_from_user(
                    owner_role_id,
                    self.config.organization_id,
                    self.config.ldap_username,
                )
                logger.info("Successfully revoked IQ Server 'Owner' role.")

        # 3. Delete privilege and repository
        self.nexus.delete_privilege(self.config.privilege_name)
        logger.info("Successfully deleted privilege.")

        self.nexus.delete_repository(self.config.repository_name)
        logger.info("Successfully deleted repository.")
