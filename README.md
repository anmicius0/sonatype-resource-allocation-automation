Okay, let's rewrite the entire README to prioritize readability, clarity, and user-friendliness. We'll structure it like a standard open-source project README, starting with a clear overview and progressing to detailed usage and configuration.

---

# Sonatype Resource Auto Allocation API (FastAPI)

[![Python 3.x](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/your-repo/your-project/releases/tag/v1.0.0)

## Overview

The Sonatype Resource Auto Allocation API is a FastAPI service designed to automate common administrative tasks across Sonatype Nexus Repository Manager and Sonatype IQ Server. It provides a simple HTTP API to:

- **Create/Delete Nexus proxy repositories** for various package managers.
- **Manage Nexus privileges and roles** associated with these repositories.
- **Assign/Revoke "Owner" permissions** for organizations in Sonatype IQ Server.

This tool streamlines the process of onboarding new teams or applications by programmatically provisioning necessary Sonatype resources.

## Features

- **Automated Nexus Management**: Create and delete proxy repositories, privileges, and roles.
- **IQ Server Integration**: Grant and revoke "Owner" role memberships for specific organizations.
- **Flexible Repository Types**: Support for both shared and application-specific repositories.
- **Batch Operations**: Process multiple repository creation/deletion requests in a single API call.
- **Configurable**: Easy customization via environment variables and JSON files.
- **Secure**: Uses HTTP Bearer token authentication.
- **Logging**: Detailed logging for monitoring and troubleshooting.

## Quick Start

### 1. Project Structure

```
├── create-repo                 # Binary (Linux/macOS)
├── create-repo.exe             # Binary (Windows)
├── config/
│   ├── .env.example            # Example environment variables
│   ├── organisations.json      # Mapping of Chinese names to IQ Server Organization IDs
│   └── package_manager.json    # Configuration for supported package managers
├── logs/                       # Log files will be generated here
└── src/                        # Source code
    └── create_repo/
        ├── api.py              # FastAPI application & endpoints
        ├── clients.py          # Nexus & IQ Server API clients
        ├── config.py           # Configuration loading & data classes
        ├── core.py             # Business logic (PrivilegeManager)
        ├── common.py           # Utilities, logging, exceptions
        └── __main__.py         # Application entry point
```

### 2. Configuration Setup

Copy the example environment file:

```bash
cp config/.env.example config/.env
```

Now, edit `config/.env` and fill in the required variables:

**Required Environment Variables:**

| Variable            | Description                                                     | Example Value                      |
| :------------------ | :-------------------------------------------------------------- | :--------------------------------- |
| `NEXUS_URL`         | Base URL of your Nexus Repository Manager.                      | `http://nexus.example.com`         |
| `NEXUS_USERNAME`    | Username for Nexus API access.                                  | `admin`                            |
| `NEXUS_PASSWORD`    | Password for Nexus API access.                                  | `admin123`                         |
| `IQSERVER_URL`      | Base URL of your Sonatype IQ Server.                            | `http://iqserver.example.com:8070` |
| `IQSERVER_USERNAME` | Username for IQ Server API access.                              | `admin`                            |
| `IQSERVER_PASSWORD` | Password for IQ Server API access.                              | `admin123`                         |
| `API_TOKEN`         | **Your secret token for authenticating with this API service.** | `my_super_secret_api_token`        |

**Optional Environment Variables:**

| Variable     | Description                                                                             | Default Value |
| :----------- | :-------------------------------------------------------------------------------------- | :------------ |
| `API_HOST`   | The host address the FastAPI service will bind to.                                      | `127.0.0.1`   |
| `PORT`       | The port the FastAPI service will listen on.                                            | `5000`        |
| `LOG_LEVEL`  | Minimum logging level (`INFO`, `DEBUG`, `WARNING`, `ERROR`).                            | `INFO`        |
| `DEBUG`      | If `true`, the service uses `organisations-debug.json` instead of `organisations.json`. | `false`       |
| `EXTRA_ROLE` | Comma-separated list of additional Nexus roles to assign to a user upon creation.       | (None)        |

### 3. Run the Service

You have two options to run the service:

**A. Using the Binary (Recommended for Production)**

1.  Download the appropriate binary for your OS from releases or build it yourself.
2.  Navigate to the directory containing the binary.
3.  Execute the binary:
    - **Linux/macOS:** `./create-repo`
    - **Windows:** `create-repo.exe`

**B. From Source (For Development)**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/your-project.git
    cd your-project
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run the application:**
    ```bash
    python -m create_repo
    ```

### 4. Verify Service Health

Once running, open your browser or use `curl` to check the health endpoint:

```bash
curl http://127.0.0.1:5000/api/health
```

**Expected Response:**

```json
{ "success": true, "status": "healthy" }
```

### 5. Logging

Application logs are written to: `./logs/app.log`

Logs are rotated automatically (5MB max size, 3 backups).

## Customization

### `config/organisations.json`

This file maps human-readable Chinese organization names to their Sonatype IQ Server internal IDs. These IDs are crucial for assigning IQ Server "Owner" permissions.

**Example:**

```json
[
  {
    "id": "ORG-ABCDEF123456",
    "name": "Logistics Applications Department",
    "chineseName": "後勤應用系統部"
  },
  {
    "id": "ORG-7890UVWXYZ",
    "name": "Finance Systems Division",
    "chineseName": "財務系統部"
  }
]
```

_The `id` field is the IQ Server organization ID. The `chineseName` is used in API requests._

### `config/package_manager.json`

This file defines the supported package manager formats and their specific configurations for Nexus.

**Structure:**

```json
{
  "supported_formats": {
    "npm": {
      "default_url": "https://registry.npmjs.org/",
      "proxy_supported": true,
      "api_endpoint": {
        "path": "/service/rest/v1/repositories/npm/proxy",
        "format_specific_config": {
          "npm": {
            "noContentFile": true,
            "removeNonManaged": true
          }
        }
      },
      "privilege_format": "npm"
    },
    "maven2": {
      "default_url": "https://repo.maven.apache.org/maven2/",
      "proxy_supported": true,
      "api_endpoint": {
        "path": "/service/rest/v1/repositories/maven/proxy",
        "format_specific_config": {
          "maven": {
            "layoutPolicy": "PERMISSIVE",
            "versionPolicy": "RELEASE"
          }
        }
      },
      "privilege_format": "maven2"
    }
  }
}
```

**Key Fields within `supported_formats.<format>`:**

- `default_url`: The remote URL for the proxy repository.
- `proxy_supported`: `true` if this format supports proxy repositories.
- `api_endpoint.path`: The specific Nexus REST API endpoint for creating this type of proxy (e.g., `/service/rest/v1/repositories/npm/proxy`).
- `api_endpoint.format_specific_config`: (Optional) Additional Nexus-specific configurations for this format.
- `privilege_format`: (Optional) The format to use when creating Nexus privileges. Defaults to the package manager name if not specified.
- `default_config`: (Optional) General default configurations to be merged into the repository creation payload.

## API Usage

The API base URL is `http://API_HOST:PORT/api`. All endpoints require **HTTP Bearer Token** authentication.

**Authentication Header:**
`Authorization: Bearer <YOUR_API_TOKEN>`

### 1. Health Check

`GET /api/health`

**Description:** Checks if the API service is running and responsive.
**Response:** `{"success": true, "status": "healthy"}`

### 2. Create Repositories (Batch)

`POST /api/repositories`

**Description:** Creates one or more Nexus proxy repositories, their associated Nexus privileges and roles, and assigns IQ Server "Owner" permissions.

**Request Body:**
A JSON object with the following structure:

```json
{
  "requests": [
    {
      "organization_name_chinese": "後勤應用系統部",
      "ldap_username": "john.doe",
      "package_manager": "npm",
      "shared": false,
      "app_id": "frontend-app"
    },
    {
      "organization_name_chinese": "財務系統部",
      "ldap_username": "jane.smith",
      "package_manager": "maven2",
      "shared": true
      // app_id is not required for shared=true
    }
  ],
  "fail_fast": true // Optional, default is true
}
```

**Request `requests` Array - Individual Request Fields:**

| Field Name                  | Type      | Required      | Description                                                                                                                                                                                                                    |
| :-------------------------- | :-------- | :------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `organization_name_chinese` | `string`  | Yes           | The Chinese name of the organization. Must match an entry in `config/organisations.json`.                                                                                                                                      |
| `ldap_username`             | `string`  | Yes           | The LDAP username of the user to be granted access and IQ Server "Owner" role. This user must exist in Nexus.                                                                                                                  |
| `package_manager`           | `string`  | Yes           | The package manager format (e.g., "npm", "maven2"). Must be defined in `config/package_manager.json`.                                                                                                                          |
| `shared`                    | `boolean` | Yes           | If `true`, the repository is shared and its privilege is added to the `repositories.share` Nexus role. If `false`, a dedicated Nexus role is created for `ldap_username` and assigned to them, and `app_id` becomes mandatory. |
| `app_id`                    | `string`  | Conditionally | **Required if `shared` is `false`**. A unique identifier for the specific application. This is used in the repository and privilege naming (e.g., `npm-release-frontend-app`).                                                 |

**Generated Names:**

- **Repository Name**: `<package_manager>-release-<app_id | 'shared'>` (e.g., `npm-release-frontend-app` or `maven2-release-shared`)
- **Privilege Name**: Same as the repository name (suffixed with `-view` internally by Nexus, but referred to by the base name in this API).
- **Role Name**:
  - If `shared` is `true`: `repositories.share`
  - If `shared` is `false`: The `ldap_username` provided in the request.
- **IQ Server**: Grants "Owner" role for the organization specified by `organization_name_chinese` to `ldap_username`.

**Curl Example (Create non-shared npm repo):**

```bash
curl -X POST "http://127.0.0.1:5000/api/repositories" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "requests": [
          {
            "organization_name_chinese": "後勤應用系統部",
            "ldap_username": "john.doe",
            "package_manager": "npm",
            "shared": false,
            "app_id": "frontend-app"
          }
        ],
        "fail_fast": true
      }'
```

### 3. Delete Repositories (Batch)

`DELETE /api/repositories`

**Description:** Deletes one or more Nexus proxy repositories and revokes associated privileges, roles, and IQ Server "Owner" permissions.

**Request Body:**
The request body is **identical** in structure to the `POST /api/repositories` endpoint.

**Deletion Behavior:**

- **For `shared: true` requests:**
  - The privilege for the specified repository is **removed from the `repositories.share` Nexus role**.
  - The underlying Nexus repository and the privilege object **are NOT deleted**, as they may be in use by other shared mappings.
  - No Nexus user role or IQ Server permission changes occur.
- **For `shared: false` requests:**
  - The specific privilege for the repository is **removed from the `ldap_username`'s dedicated Nexus role**.
  - If this action leaves the `ldap_username`'s role empty of privileges, the role is **deleted** from Nexus.
  - The Nexus user's roles are updated (the `ldap_username`'s role is removed if it was deleted).
  - The IQ Server "Owner" role is **revoked** for the `ldap_username` in the specified organization.
  - The Nexus privilege object (e.g., `npm-release-frontend-app-view`) is **deleted**.
  - The Nexus proxy repository (e.g., `npm-release-frontend-app`) is **deleted**.

**Curl Example (Delete shared maven2 mapping):**

```bash
curl -X DELETE "http://127.0.0.1:5000/api/repositories" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "requests": [
          {
            "organization_name_chinese": "後勤應用系統部",
            "ldap_username": "jane.smith",
            "package_manager": "maven2",
            "shared": true
          }
        ],
        "fail_fast": false
      }'
```

### 4. Batch Operation Response Structure

Both `POST` and `DELETE` batch endpoints return a common JSON response:

```json
{
  "success": true, // Overall status: true if all requests processed successfully, false otherwise.
  "message": "Processed 1 of 2 requests successfully", // Summary message.
  "processed_count": 1, // Number of requests for which an attempt was made.
  "total_requests": 2, // Total number of requests provided in the batch.
  "results": [
    // Array of details for successfully processed requests. Empty if all failed.
    {
      "index": 0, // 0-based index of the original request in the batch.
      "success": true,
      "data": {
        /* Detailed information about the successfully performed action */
      },
      "message": "Successfully created repository and privileges"
    }
  ],
  "errors": [
    // Optional: Array of error details for failed requests. Null if no errors.
    {
      "index": 1,
      "success": false,
      "error": "app_id is required for non-shared repositories", // Error message.
      "request": {
        /* The original request payload that caused the error */
      }
    }
  ]
}
```

### 5. Error Handling

The API uses standard HTTP status codes to indicate the outcome of a request, along with a `success: false` and `error` message in the JSON body for detailed context.

| Status Code | Error Type           | Description                                                                                                                                                               |
| :---------- | :------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `401`       | Unauthorized         | The `Authorization` header is missing or the provided `API_TOKEN` is invalid.                                                                                             |
| `400`       | `ValidationError`    | The request payload is invalid, incomplete, or violates business rules (e.g., `app_id` missing for non-shared repo, unsupported package manager, organization not found). |
| `500`       | `ConfigurationError` | An internal server configuration issue (e.g., Nexus/IQ Server credentials not found, problem with internal config files).                                                 |
| `500`       | Other Internal Error | An unexpected error occurred within the service or during communication with Nexus/IQ Server. Review logs for details.                                                    |

## Troubleshooting Common Issues

- **`401 Invalid token`**:
  - Ensure your `API_TOKEN` in `config/.env` is correctly set and is exactly what you are sending in the `Authorization: Bearer` header.
- **`400 app_id is required for non-shared repositories`**:
  - If `shared` is `false` in your request, you **must** provide a non-empty `app_id` string.
- **`400 Package manager 'xyz' is not supported`**:
  - Check `config/package_manager.json`. The `package_manager` in your request must exactly match one of the keys under `supported_formats` (e.g., `npm`, `maven2`).
- **`500 Organization '組織名稱' not found`**:
  - The `organization_name_chinese` in your request must precisely match a `chineseName` entry in `config/organisations.json`. Check for typos or missing entries.
- **`500 User 'ldap.username' not found in Nexus`**:
  - The `ldap_username` must exist as a user in your Nexus Repository Manager instance.
- **API not running / Connection refused**:
  - Verify the service is actually running. Check the console where you launched it, or look for `app.log` in the `logs/` directory.
  - Confirm that `API_HOST` and `PORT` in `config/.env` match the URL you are attempting to connect to.
- **Nexus/IQ Server connectivity issues**:
  - Check the `NEXUS_URL`, `IQSERVER_URL`, and respective credentials in `config/.env`.
  - Ensure network connectivity from the API server to your Nexus and IQ Server instances. Review `app.log` for more specific connection errors.

## Development & Maintenance

### Code Structure (`src/create_repo`)

- `__main__.py`: Application entry point. Loads environment variables, configures logging, and starts the Uvicorn server.
- `api.py`: Defines the FastAPI application, Pydantic models for request/response, authentication dependency (`HTTPBearer`), and the API endpoints (`/api/health`, `/api/repositories`).
- `clients.py`: Contains `APIClient` (base for HTTP requests with retries), `NexusClient` (for Nexus Repository Manager interactions), and `IQServerClient` (for Sonatype IQ Server interactions).
- `config.py`: Handles loading application-wide configurations (Nexus/IQ Server credentials, organization mappings, package manager details) and creates `OperationConfig` dataclasses.
- `core.py`: Encapsulates the core business logic in the `PrivilegeManager` class, orchestrating calls to Nexus and IQ Server clients to perform create/delete operations.
- `common.py`: Provides shared utilities such as custom exceptions (`ValidationError`, `ConfigurationError`), application path resolution, JSON file loading, CSV parsing, and detailed logging configuration.

### Local Development Setup

1.  Navigate to the project root.
2.  Create and activate a Python virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Run the application:
    ```bash
    python -m create_repo
    ```
    _Tip_: Set `DEBUG=true` in `config/.env` to use `organisations-debug.json` for testing.

## Security Considerations

- **Keep `API_TOKEN` Secret**: Treat your `API_TOKEN` like a password. Do not expose it publicly or commit it to version control.
- **Credential Security**: Store Nexus and IQ Server credentials securely using environment variables, as recommended.
- **Least Privilege**: Ensure the Nexus and IQ Server accounts used by this API have only the minimum necessary permissions to perform their tasks.
- **Reverse Proxy**: For production deployments, it is highly recommended to place this API behind a reverse proxy (e.g., Nginx, Caddy) for SSL/TLS encryption, rate limiting, and additional security layers.
