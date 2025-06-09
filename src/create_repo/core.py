"""
Core business logic for Nexus repository and privilege management.
"""

import logging
from typing import Dict, Any

from create_repo.clients import NexusClient, IQServerClient
from create_repo.config import OperationConfig
from create_repo.common import ConfigurationError

logger = logging.getLogger(__name__)


class PrivilegeManager:
    """Orchestrates the creation and deletion of Nexus and IQ Server resources."""

    def __init__(self, config: OperationConfig, nexus: NexusClient, iq: IQServerClient):
        self.config = config
        self.nexus = nexus
        self.iq = iq

    def run(self) -> Dict[str, Any]:
        """Executes the requested operation ('create' or 'delete')."""
        logger.info(
            f"Starting {self.config.action} operation for repository '{self.config.repository_name}'"
        )
        logger.debug(
            f"Operation config - User: {self.config.ldap_username}, "
            f"Organization: {self.config.organization_id}, "
            f"Package Manager: {self.config.package_manager}, "
            f"Role: {self.config.role_name}"
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
        """Creates all required resources in Nexus and IQ Server."""
        logger.debug("=== Starting resource creation process ===")

        # 1. Create repository if it doesn't exist
        logger.debug("Step 1: Repository creation/verification")
        if not self.nexus.get_repository(self.config.repository_name):
            logger.info(f"Creating repository: {self.config.repository_name}")
            self.nexus.create_proxy_repository(self.config)
            logger.info(
                f"✓ Repository '{self.config.repository_name}' created successfully"
            )
        else:
            logger.info(
                f"✓ Repository '{self.config.repository_name}' already exists - skipping creation"
            )

        # 2. Create privilege if it doesn't exist
        logger.debug("Step 2: Privilege creation/verification")
        if not self.nexus.get_privilege(self.config.privilege_name):
            logger.info(f"Creating privilege: {self.config.privilege_name}")
            self.nexus.create_privilege(self.config)
            logger.info(
                f"✓ Privilege '{self.config.privilege_name}' created successfully"
            )
        else:
            logger.info(
                f"✓ Privilege '{self.config.privilege_name}' already exists - skipping creation"
            )

        # 3. Create or update role
        logger.debug("Step 3: Role creation/update")
        role = self.nexus.get_role(self.config.role_name)
        if role is None:
            logger.info(f"Creating new role: {self.config.role_name}")
            self.nexus.create_role(self.config)
            logger.info(f"✓ Role '{self.config.role_name}' created successfully")
        elif self.config.privilege_name not in role.get("privileges", []):
            logger.info(
                f"Adding privilege '{self.config.privilege_name}' to existing role '{self.config.role_name}'"
            )
            role["privileges"].append(self.config.privilege_name)
            self.nexus.update_role(role)
            logger.info(
                f"✓ Privilege added to role '{self.config.role_name}' successfully"
            )
        else:
            logger.info(
                f"✓ Role '{self.config.role_name}' already has required privilege - skipping update"
            )

        # 4. Update user roles
        logger.debug("Step 4: User role assignment")
        user = self.nexus.get_user(self.config.ldap_username)
        if not user:
            logger.error(f"User '{self.config.ldap_username}' not found in Nexus")
            raise ConfigurationError(
                f"User '{self.config.ldap_username}' not found in Nexus."
            )

        current_roles = set(user.get("roles", []))
        required_roles = set([self.config.role_name] + self.config.extra_roles)

        logger.debug(f"Current user roles: {sorted(current_roles)}")
        logger.debug(f"Required roles: {sorted(required_roles)}")

        if not required_roles.issubset(current_roles):
            new_roles = sorted(list(current_roles | required_roles))
            logger.info(
                f"Adding required roles to user '{self.config.ldap_username}': {sorted(required_roles - current_roles)}"
            )
            user["roles"] = new_roles
            self.nexus.update_user(user)
            logger.info(
                f"✓ User roles updated successfully. New role list: {new_roles}"
            )
        else:
            logger.info(
                f"✓ User '{self.config.ldap_username}' already has all required roles - skipping update"
            )

        # 5. IQ Server setup (if organization_id provided)
        if self.config.organization_id:
            logger.debug("Step 5: IQ Server permissions setup")
            logger.info("Setting up IQ Server permissions")
            owner_role_id = self.iq.find_owner_role_id()
            if owner_role_id:
                logger.debug(f"Found Owner role ID: {owner_role_id}")
                self.iq.grant_role_to_user(
                    owner_role_id,
                    self.config.organization_id,
                    self.config.ldap_username,
                )
                logger.info(
                    f"✓ Successfully granted 'Owner' role to '{self.config.ldap_username}' in IQ Server organization '{self.config.organization_id}'"
                )
            else:
                logger.warning(
                    "Could not find 'Owner' role in IQ Server - skipping IQ permissions"
                )
        else:
            logger.debug(
                "Step 5: Skipping IQ Server setup (no organization_id provided)"
            )

        logger.debug("=== Resource creation process completed ===")

    def _delete_resources(self) -> None:
        """Deletes or cleans up resources based on repository type."""
        logger.debug("=== Starting resource deletion process ===")
        logger.info(
            f"Starting resource cleanup for repository '{self.config.repository_name}'"
        )

        # For shared repositories, only remove privilege from shared role
        if self.config.role_name == "repositories.share":
            logger.debug("Processing shared repository deletion")
            logger.info("Shared repository: removing privilege from shared role")
            role = self.nexus.get_role(self.config.role_name)
            if role and self.config.privilege_name in role.get("privileges", []):
                logger.debug(
                    f"Removing privilege '{self.config.privilege_name}' from shared role"
                )
                role["privileges"].remove(self.config.privilege_name)
                self.nexus.update_role(role)
                logger.info(
                    f"✓ Successfully removed privilege '{self.config.privilege_name}' from shared role"
                )
            else:
                logger.info("✓ Privilege not found in shared role - nothing to remove")
            logger.debug("=== Shared repository cleanup completed ===")
            return

        logger.debug("Processing non-shared repository deletion")

        # For non-shared repositories, perform full cleanup
        # 1. Clean up role
        logger.debug("Step 1: Role cleanup")
        role = self.nexus.get_role(self.config.role_name)
        if role:
            privileges = set(role.get("privileges", []))
            logger.debug(
                f"Role '{self.config.role_name}' currently has privileges: {sorted(privileges)}"
            )

            if self.config.privilege_name in privileges:
                privileges.remove(self.config.privilege_name)
                logger.debug(
                    f"Removed privilege '{self.config.privilege_name}' from role"
                )

                if not privileges:
                    logger.info(
                        f"Role '{self.config.role_name}' will be empty after privilege removal - deleting role"
                    )
                    # Remove role from user first, then delete empty role
                    user = self.nexus.get_user(self.config.ldap_username)
                    if user:
                        original_roles = user.get("roles", [])
                        user["roles"] = [
                            r for r in original_roles if r != self.config.role_name
                        ]
                        logger.debug(
                            f"Removing role '{self.config.role_name}' from user '{self.config.ldap_username}'"
                        )
                        self.nexus.update_user(user)
                        logger.info(
                            f"✓ Removed role from user '{self.config.ldap_username}'"
                        )

                    self.nexus.delete_role(self.config.role_name)
                    logger.info(f"✓ Deleted empty role '{self.config.role_name}'")
                else:
                    logger.info(
                        f"Role '{self.config.role_name}' still has other privileges - updating role"
                    )
                    role["privileges"] = list(privileges)
                    self.nexus.update_role(role)
                    logger.info(
                        f"✓ Updated role '{self.config.role_name}' with remaining privileges: {sorted(privileges)}"
                    )
            else:
                logger.info(
                    f"✓ Privilege '{self.config.privilege_name}' not found in role '{self.config.role_name}' - skipping role update"
                )
        else:
            logger.info(
                f"✓ Role '{self.config.role_name}' not found - skipping role cleanup"
            )

        # 2. IQ Server cleanup
        if self.config.organization_id:
            logger.debug("Step 2: IQ Server permissions cleanup")
            logger.info("Revoking IQ Server permissions")
            owner_role_id = self.iq.find_owner_role_id()
            if owner_role_id:
                logger.debug(
                    f"Found Owner role ID: {owner_role_id} - revoking permissions"
                )
                self.iq.revoke_role_from_user(
                    owner_role_id,
                    self.config.organization_id,
                    self.config.ldap_username,
                )
                logger.info(
                    f"✓ Successfully revoked IQ Server 'Owner' role from '{self.config.ldap_username}' in organization '{self.config.organization_id}'"
                )
            else:
                logger.warning(
                    "Could not find 'Owner' role in IQ Server - skipping IQ permissions cleanup"
                )
        else:
            logger.debug(
                "Step 2: Skipping IQ Server cleanup (no organization_id provided)"
            )

        # 3. Delete privilege and repository
        logger.debug("Step 3: Privilege deletion")
        self.nexus.delete_privilege(self.config.privilege_name)
        logger.info(f"✓ Successfully deleted privilege '{self.config.privilege_name}'")

        logger.debug("Step 4: Repository deletion")
        self.nexus.delete_repository(self.config.repository_name)
        logger.info(
            f"✓ Successfully deleted repository '{self.config.repository_name}'"
        )

        logger.debug("=== Resource deletion process completed ===")
