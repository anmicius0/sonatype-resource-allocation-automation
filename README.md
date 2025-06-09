# Nexus Privilege Management Tool

Automates creation and deletion of Nexus Repository Manager resources including repositories, privileges, roles, and user permissions.

## Quick Start

1. Install dependencies: `pip install requests python-dotenv`
2. Create `.env` file with required variables
3. Run: `python main.py create` or `python main.py delete`

## Configuration

Create a `.env` file:

```env
NEXUS_URL=https://your-nexus-instance.com
NEXUS_USERNAME=admin-user
NEXUS_PASSWORD=admin-password
LDAP_USERNAME=your-ldap-username
APP_ID=your-app-id
PACKAGE_MANAGER=npm  # or 'go'
SHARED=false  # true for shared repositories
DEFAULT_ROLES=role1,role2  # optional
```

## Workflow Logic

### Create Workflow

```
1. Repository Creation
   ├── Check if repository exists
   ├── Create proxy repository if missing
   └── Configure with appropriate remote URL

2. Privilege Creation
   ├── Check if privilege exists
   ├── Create repository-view privilege if missing
   └── Grant BROWSE, READ, EDIT, ADD, DELETE permissions

3. Role Management
   ├── Check if user role exists
   ├── Create role if missing
   ├── Link privilege to role
   └── Ensure role has required privilege

4. User Assignment
   ├── Verify LDAP user exists
   ├── Get current user roles
   ├── Add new role + any extra roles
   └── Update user permissions
```

### Delete Workflow

```
1. Role & User Unlinking
   ├── Remove privilege from role
   ├── Check if role becomes empty
   ├── If empty: unlink role from user
   └── If empty: delete the role

2. Privilege Deletion
   ├── Remove the repository privilege
   └── Handle missing privilege gracefully

3. Repository Cleanup
   ├── Delete the repository
   └── Handle missing repository gracefully
```

## Repository Naming

- Regular: `{package_manager}-release-{app_id}`
- Shared: `{package_manager}-release-share`

Examples: `npm-release-myapp`, `go-release-share`

## Supported Package Managers

| Package Manager | Remote URL                  |
| --------------- | --------------------------- |
| npm             | https://registry.npmjs.org/ |
| go              | https://proxy.golang.org/   |

## Example Usage

```bash
# Create npm repository for specific app
APP_ID=frontend-app PACKAGE_MANAGER=npm python main.py create

# Create shared Go repository
PACKAGE_MANAGER=go SHARED=true python main.py create

# Delete resources
python main.py delete
```
