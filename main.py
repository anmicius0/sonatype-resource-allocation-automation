#!/usr/bin/env python3
"""
Nexus Repository Manager User Privilege Management Tool
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        required_environment_variables = [
            "NEXUS_URL",
            "NEXUS_USERNAME",
            "NEXUS_PASSWORD",
            "PRIVILEGE_NAME",
            "APP_ID",
            "FRAMEWORK",
            "USER_ID",
        ]

        missing_variables = [
            var for var in required_environment_variables if not os.getenv(var)
        ]
        if missing_variables:
            raise ValueError(
                f"Missing environment variables: {', '.join(missing_variables)}"
            )

        self.nexus_url = os.getenv("NEXUS_URL")
        self.nexus_username = os.getenv("NEXUS_USERNAME")
        self.nexus_password = os.getenv("NEXUS_PASSWORD")
        self.privilege_name = os.getenv("PRIVILEGE_NAME")
        self.privilege_description = os.getenv(
            "PRIVILEGE_DESCRIPTION", "Custom privilege"
        )
        self.app_id = os.getenv("APP_ID")
        self.framework = os.getenv("FRAMEWORK")
        self.user_id = os.getenv("USER_ID")

        self.role_name = self.user_id
        self.repository_name = f"{self.framework}-release-{self.app_id}"

        # Read default roles from environment variable (comma-separated)
        self.default_roles = [
            role.strip()
            for role in os.getenv("DEFAULT_ROLES", "").split(",")
            if role.strip()
        ]


class NexusClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        return response

    def test_connection(self):
        try:
            response = self._request("GET", "/service/rest/v1/status")
            return response.status_code == 200
        except:
            return False

    def repository_exists(self, repository_name):
        try:
            response = self._request(
                "GET", f"/service/rest/v1/repositories/{repository_name}"
            )
            return response.status_code == 200
        except:
            return False

    def create_repository(self, repository_name, framework):
        repository_config = {
            "name": repository_name,
            "online": True,
            "storage": {
                "blobStoreName": "default",
                "strictContentTypeValidation": True,
                "writePolicy": "ALLOW",
            },
            "cleanup": {"policyNames": []},
            "component": {"proprietaryComponents": True},
        }

        try:
            response = self._request(
                "POST",
                f"/service/rest/v1/repositories/{framework}/hosted",
                json=repository_config,
            )
            return response.status_code == 201
        except:
            return False

    def create_privilege(
        self, privilege_name, privilege_description, repository_name, framework
    ):
        privilege_config = {
            "name": privilege_name,
            "description": privilege_description,
            "actions": ["BROWSE", "READ", "EDIT", "ADD", "DELETE"],
            "format": framework,
            "repository": repository_name,
        }

        try:
            response = self._request(
                "POST",
                "/service/rest/v1/security/privileges/repository-view",
                json=privilege_config,
            )
            return response.status_code == 201
        except:
            return False

    def get_privilege(self, privilege_name):
        try:
            response = self._request(
                "GET", f"/service/rest/v1/security/privileges/{privilege_name}"
            )
            return response.json() if response.status_code == 200 else None
        except:
            return None

    def get_role(self, role_name):
        try:
            response = self._request(
                "GET", f"/service/rest/v1/security/roles/{role_name}"
            )
            return response.json() if response.status_code == 200 else None
        except:
            return None

    def create_role(self, role_name, role_description, privilege_list):
        role_config = {
            "id": role_name,
            "name": role_name,
            "description": role_description,
            "privileges": privilege_list,
            "roles": [],
        }

        try:
            response = self._request(
                "POST", "/service/rest/v1/security/roles", json=role_config
            )
            return response.status_code in [200, 201]
        except:
            return False

    def add_privilege_to_role(self, role_name, privilege_name):
        existing_role = self.get_role(role_name)
        if not existing_role:
            return False

        current_privileges = existing_role.get("privileges", [])
        if privilege_name in current_privileges:
            return True

        current_privileges.append(privilege_name)
        updated_role_data = {
            "id": existing_role["id"],
            "name": existing_role["name"],
            "description": existing_role.get("description", ""),
            "privileges": current_privileges,
            "roles": existing_role.get("roles", []),
        }

        try:
            response = self._request(
                "PUT",
                f"/service/rest/v1/security/roles/{role_name}",
                json=updated_role_data,
            )
            return response.status_code == 204
        except:
            return False

    def get_user(self, user_id):
        try:
            response = self._request(
                "GET", "/service/rest/v1/security/users", params={"userId": user_id}
            )
            if response.status_code == 200:
                user_list = response.json()
                for user_data in user_list:
                    if user_data.get("userId") == user_id:
                        return user_data
            return None
        except:
            return None

    def add_role_to_user(self, user_id, role_name):
        existing_user = self.get_user(user_id)
        if not existing_user:
            return False

        current_roles = existing_user.get("roles", [])
        if role_name in current_roles:
            return True

        current_roles.append(role_name)
        updated_user_data = {
            "userId": existing_user["userId"] or user_id,
            "firstName": existing_user.get("firstName") or "Unknown",
            "lastName": existing_user.get("lastName") or "User",
            "emailAddress": existing_user.get("emailAddress")
            or f"{user_id}@example.com",
            "source": existing_user.get("source") or "default",
            "status": existing_user.get("status") or "active",
            "roles": current_roles,
        }

        try:
            response = self._request(
                "PUT",
                f"/service/rest/v1/security/users/{user_id}",
                json=updated_user_data,
            )
            return response.status_code == 204
        except:
            return False


class PrivilegeManager:
    def __init__(self, config):
        self.config = config
        self.nexus = NexusClient(
            config.nexus_url, config.nexus_username, config.nexus_password
        )

    # Helper method to unify check-and-create logic
    def _ensure_entity(self, entity_type, exists_function, create_function, *args):
        print(f"\nChecking {entity_type} '{args[0]}'...")
        if not exists_function(*args):
            print(f"   Creating {entity_type}...")
            if not create_function(*args):
                raise RuntimeError(f"{entity_type.title()} {args[0]} creation failed")
        print(f"   ✅ {entity_type.title()} ready")

    def run(self):
        print("🔧 Nexus Privilege Management Tool")
        print("=" * 40)

        # Test connection
        if not self.nexus.test_connection():
            raise RuntimeError("Failed to connect to Nexus server")
        print("✅ Connected to Nexus")

        # Ensure repository and privilege
        print(f"\nChecking repository '{self.config.repository_name}'...")
        if not self.nexus.repository_exists(self.config.repository_name):
            print("   Creating repository...")
            if not self.nexus.create_repository(
                self.config.repository_name, self.config.framework
            ):
                raise RuntimeError(
                    f"Repository {self.config.repository_name} creation failed"
                )
        print("   ✅ Repository ready")
        self._ensure_entity(
            "privilege",
            self.nexus.get_privilege,
            lambda privilege_name: self.nexus.create_privilege(
                privilege_name,
                self.config.privilege_description,
                self.config.repository_name,
                self.config.framework,
            ),
            self.config.privilege_name,
        )

        # Ensure role and assign privilege
        role_name = self.config.role_name
        print(f"\nChecking role '{role_name}'...")
        existing_role = self.nexus.get_role(role_name)
        if not existing_role:
            print("   Creating role...")
            if not self.nexus.create_role(
                role_name,
                f"Role for {self.config.app_id}",
                [self.config.privilege_name],
            ):
                raise RuntimeError(f"Role {role_name} creation failed")
        else:
            print("   Adding privilege to role...")
            if not self.nexus.add_privilege_to_role(
                role_name, self.config.privilege_name
            ):
                raise RuntimeError(f"Adding privilege to role {role_name} failed")
        print("   ✅ Role ready")

        # Assign roles to user
        print(f"\nAdding role to user '{self.config.user_id}'...")
        for role_to_assign in set([role_name] + self.config.default_roles):
            if not self.nexus.add_role_to_user(self.config.user_id, role_to_assign):
                raise RuntimeError(f"Failed to add role '{role_to_assign}' to user")
        print("   ✅ User updated")

        print("\n🎉 All operations completed successfully!")


def main():
    config = Config()
    manager = PrivilegeManager(config)
    try:
        manager.run()
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"💥 {e}")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
