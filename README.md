# Nexus Repository Manager Setup Tool

Automates the creation of repositories, privileges, roles, and user assignments in Nexus Repository Manager.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables in `.env` file

3. Run the tool:
   ```bash
   python main.py
   ```

## Environment Variables

| Variable                | Description                        | Example                                        |
| ----------------------- | ---------------------------------- | ---------------------------------------------- |
| `NEXUS_URL`             | Nexus server URL                   | `http://35.208.159.14:8081`                    |
| `NEXUS_USERNAME`        | Admin username                     | `admin`                                        |
| `NEXUS_PASSWORD`        | Admin password                     | `admin123`                                     |
| `PRIVILEGE_NAME`        | Custom privilege name              | `ap.dso.skynet`                                |
| `PRIVILEGE_DESCRIPTION` | Privilege description              | `Full access privilege for skynet application` |
| `APP_ID`                | Application identifier             | `skynet`                                       |
| `FRAMEWORK`             | Repository type                    | `npm`                                          |
| `USER_ID`               | Target user ID                     | `ap.dso.skynet`                                |
| `DEFAULT_ROLES`         | Additional roles (comma-separated) | `role1,role2`                                  |

## What it does

1. **Creates repository**: `{FRAMEWORK}-release-{APP_ID}`
2. **Creates privilege**: With full access to the repository
3. **Creates role**: Named after `USER_ID` with the privilege assigned
4. **Assigns roles**: Adds the role + default roles to the user

## Requirements

- Python 3.6+
- Nexus Repository Manager with admin access
- Valid `.env` configuration
