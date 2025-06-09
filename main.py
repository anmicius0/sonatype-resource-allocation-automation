import os
import sys
import argparse
import requests
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Set
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    action: str
    nexus_url: str
    nexus_username: str
    nexus_password: str
    ldap_username: str
    remote_url: str
    extra_roles: List[str]
    repository_name: str
    privilege_name: str
    role_name: str
    package_manager: str

    @classmethod
    def from_env_and_args(cls) -> "Config":
        parser = argparse.ArgumentParser()
        parser.add_argument("action", choices=["create", "delete"])
        action = parser.parse_args().action
        for v in [
            "NEXUS_URL",
            "NEXUS_USERNAME",
            "NEXUS_PASSWORD",
            "LDAP_USERNAME",
            "APP_ID",
            "PACKAGE_MANAGER",
        ]:
            if not os.getenv(v):
                raise ValueError(f"Missing env: {v}")
        pm = os.environ["PACKAGE_MANAGER"]
        with open(
            os.path.join(os.path.dirname(__file__), "default_repo_urls.json")
        ) as f:
            remote_urls = json.load(f)
        remote_url = remote_urls.get(pm) or remote_urls.get(pm.lower())
        if not remote_url:
            raise ValueError(f"No remote URL for {pm}")
        repo_id = (
            "share"
            if os.getenv("SHARED", "false").lower() == "true"
            else os.environ["APP_ID"]
        )
        repo_name = f"{pm}-release-{repo_id}"
        extra_roles = [
            r.strip() for r in os.getenv("DEFAULT_ROLES", "").split(",") if r.strip()
        ]
        return cls(
            action=action,
            nexus_url=os.environ["NEXUS_URL"],
            nexus_username=os.environ["NEXUS_USERNAME"],
            nexus_password=os.environ["NEXUS_PASSWORD"],
            ldap_username=os.environ["LDAP_USERNAME"],
            remote_url=remote_url,
            extra_roles=extra_roles,
            repository_name=repo_name,
            privilege_name=repo_name,
            role_name=os.environ["LDAP_USERNAME"],
            package_manager=pm,
        )


class NexusClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.auth = (username, password)
        self.s.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def _req(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}/service/rest{endpoint}"
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

    def get_repository(self, name: str) -> Optional[Dict[str, Any]]:
        r = self._req("GET", f"/v1/repositories/{name}")
        return r.json() if r.ok else None

    def create_proxy_repository(self, name: str, pm: str, remote_url: str) -> bool:
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
            "cleanup": {"policyNames": []},
        }
        r = self._req("POST", f"/v1/repositories/{pm}/proxy", json=config)
        return r.status_code == 201

    def delete_repository(self, name: str) -> bool:
        r = self._req("DELETE", f"/v1/repositories/{name}")
        return r.status_code in [204, 404]

    def get_privilege(self, name: str) -> Optional[Dict[str, Any]]:
        r = self._req("GET", f"/v1/security/privileges/{name}")
        return r.json() if r.ok else None

    def create_privilege(self, name: str, repo_name: str, pm: str) -> bool:
        config = {
            "name": name,
            "description": f"All permissions for repository '{repo_name}'",
            "actions": ["BROWSE", "READ", "EDIT", "ADD", "DELETE"],
            "format": pm,
            "repository": repo_name,
        }
        r = self._req("POST", "/v1/security/privileges/repository-view", json=config)
        return r.ok

    def delete_privilege(self, name: str) -> bool:
        r = self._req("DELETE", f"/v1/security/privileges/{name}")
        return r.status_code in [204, 404]

    def get_role(self, name: str) -> Optional[Dict[str, Any]]:
        r = self._req("GET", f"/v1/security/roles/{name}")
        return r.json() if r.ok else None

    def create_role(self, name: str, desc: str, privileges: List[str]) -> bool:
        config = {
            "id": name,
            "name": name,
            "description": desc,
            "privileges": privileges,
            "roles": [],
        }
        r = self._req("POST", "/v1/security/roles", json=config)
        return r.status_code in [200, 201]

    def update_role(self, role: Dict[str, Any]) -> bool:
        r = self._req("PUT", f"/v1/security/roles/{role['id']}", json=role)
        return r.status_code == 204

    def delete_role(self, name: str) -> bool:
        r = self._req("DELETE", f"/v1/security/roles/{name}")
        return r.status_code in [204, 404]

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        r = self._req("GET", "/v1/security/users", params={"userId": user_id})
        if r.ok:
            users = r.json()
            return next((u for u in users if u.get("userId") == user_id), None)
        return None

    def update_user(self, user: Dict[str, Any]) -> bool:
        r = self._req("PUT", f"/v1/security/users/{user['userId']}", json=user)
        return r.status_code == 204


class PrivilegeManager:
    def __init__(self, config: Config):
        self.c = config
        self.n = NexusClient(
            config.nexus_url, config.nexus_username, config.nexus_password
        )

    def run(self) -> None:
        print(
            f"\n🔧 {self.c.action.upper()} Nexus Repository: {self.c.repository_name}"
        )
        print(f"👤 User/Role: {self.c.role_name}")
        try:
            if self.c.action == "create":
                self.create()
            else:
                self.delete()
            print("\n✅ Done!")
        except Exception as e:
            print(f"\n❌ Error: {e}", file=sys.stderr)
            sys.exit(1)

    def create(self) -> None:
        print("  ➡️ Checking repository...")
        if not self.n.get_repository(self.c.repository_name):
            print("    🏗️ Creating repository...")
            if not self.n.create_proxy_repository(
                self.c.repository_name, self.c.package_manager, self.c.remote_url
            ):
                raise RuntimeError("Repository creation failed.")
        else:
            print("    ✔️ Repository exists.")
        print("  ➡️ Checking privilege...")
        if not self.n.get_privilege(self.c.privilege_name):
            print("    🏗️ Creating privilege...")
            if not self.n.create_privilege(
                self.c.privilege_name, self.c.repository_name, self.c.package_manager
            ):
                raise RuntimeError("Privilege creation failed.")
        else:
            print("    ✔️ Privilege exists.")
        self.ensure_role_and_privilege()
        self.ensure_user_and_role()

    def ensure_role_and_privilege(self) -> None:
        print("  ➡️ Checking role...")
        role = self.n.get_role(self.c.role_name)
        if not role:
            print("    🏗️ Creating role and linking privilege...")
            if not self.n.create_role(
                self.c.role_name,
                f"Role for {self.c.ldap_username}",
                [self.c.privilege_name],
            ):
                raise RuntimeError("Role creation failed.")
        elif self.c.privilege_name not in role.get("privileges", []):
            print("    🔗 Linking privilege to role...")
            role["privileges"].append(self.c.privilege_name)
            if not self.n.update_role(role):
                raise RuntimeError("Failed to link privilege to role.")
        else:
            print("    ✔️ Role and privilege link exists.")

    def ensure_user_and_role(self) -> None:
        print("  ➡️ Checking user-role link...")
        user = self.n.get_user(self.c.ldap_username)
        if not user:
            raise RuntimeError(f"User '{self.c.ldap_username}' not found.")
        current = set(user.get("roles", []))
        required = set([self.c.role_name] + self.c.extra_roles)
        if not required.issubset(current):
            print("    🔗 Linking role(s) to user...")
            user["roles"] = sorted(list(current | required))
            if not self.n.update_user(user):
                raise RuntimeError("Failed to link role to user.")
        else:
            print("    ✔️ User already has required role(s).")

    def delete(self) -> None:
        print("  ➡️ Unlinking and cleaning up...")
        self.handle_unlink()
        print("  ➡️ Deleting privilege...")
        if not self.n.delete_privilege(self.c.privilege_name):
            raise RuntimeError("Privilege deletion failed.")
        print("    🗑️ Privilege deleted.")
        print("  ➡️ Deleting repository...")
        if not self.n.delete_repository(self.c.repository_name):
            raise RuntimeError("Repository deletion failed.")
        print("    🗑️ Repository deleted.")

    def handle_unlink(self) -> None:
        role = self.n.get_role(self.c.role_name)
        if not role or self.c.privilege_name not in role.get("privileges", []):
            print("    ✔️ Role or privilege link already absent.")
            return
        privs = set(role["privileges"])
        privs.remove(self.c.privilege_name)
        if not privs:
            print("    🗑️ Role will be empty, deleting role and unlinking from user...")
            user = self.n.get_user(self.c.ldap_username)
            if user and self.c.role_name in user.get("roles", []):
                user["roles"].remove(self.c.role_name)
                if not self.n.update_user(user):
                    raise RuntimeError("Failed to unlink role from user.")
            if not self.n.delete_role(self.c.role_name):
                raise RuntimeError("Failed to delete empty role.")
            print("    🗑️ Role deleted.")
        else:
            print("    🔗 Unlinking privilege from role...")
            role["privileges"] = sorted(list(privs))
            if not self.n.update_role(role):
                raise RuntimeError("Failed to unlink privilege from role.")
            print("    ✔️ Privilege unlinked from role.")


def main() -> None:
    try:
        config = Config.from_env_and_args()
        PrivilegeManager(config).run()
    except (
        ValueError,
        RuntimeError,
        ConnectionError,
        requests.exceptions.HTTPError,
    ) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__} - {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
