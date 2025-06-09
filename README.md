# Sonatype Resource Auto Allocation

## 🚀 Quick Start

1. **Download & Extract**

   - Download the release for your OS (Windows, macOS, Linux) from the releases page.
   - Extract the archive. You should see files like:
     ```
     ./
     ├── create-repo (or create-repo.exe on Windows)
     ├── config
     │   ├── .env.example
     │   ├── organisations.json
     │   └── package_manager.json
     ├── README.md
     ```

2. **Configure Environment**

   - Copy `config/.env.example` to `config/.env`:
     ```bash
     cp config/.env.example config/.env
     ```
   - Edit `config/.env` with your server and credentials:
     ```dotenv
     NEXUS_URL=http://your-nexus-server:8081
     NEXUS_USERNAME=admin
     NEXUS_PASSWORD=your-admin-password
     IQSERVER_URL=http://your-iqserver:8070
     IQSERVER_USERNAME=your-iq-username
     IQSERVER_PASSWORD=your-iq-password
     API_TOKEN=your_secure_token_here
     PORT=5000
     DEBUG=false
     API_HOST=127.0.0.1
     LOG_LEVEL=INFO
     EXTRA_ROLE=developer,qa  # optional, comma-separated
     ```
   - See `config/.env.example` for all options.

3. **Run the API Server**
   - In terminal:
     ```bash
     ./create-repo
     ```
   - Or on Windows:
     ```cmd
     create-repo.exe
     ```
   - The server will start using the settings in `config/.env`.
   - Test health endpoint (no auth required):
     ```bash
     curl http://127.0.0.1:5000/api/health
     ```

## ⚙️ Configuration

- All environment variables are in `config/.env`.
- Organization and package manager settings are in `config/organisations.json` and `config/package_manager.json`.
- Main variables:
  - `NEXUS_URL`, `NEXUS_USERNAME`, `NEXUS_PASSWORD`: Nexus Repository credentials
  - `IQSERVER_URL`, `IQSERVER_USERNAME`, `IQSERVER_PASSWORD`: IQ Server credentials
  - `API_TOKEN`: Token for API authentication
  - `PORT`, `API_HOST`, `DEBUG`, `LOG_LEVEL`: API server settings
  - `EXTRA_ROLE`: (optional) Extra Nexus roles for users

## 🔌 REST API Usage

- **Base URL:** `http://localhost:5000/api`

### Endpoints

- **GET /api/health** — Health check

  - No authentication required.
  - Response:
    ```json
    { "success": true, "status": "healthy" }
    ```

- **POST /api/repository** — Create or delete a single repository

  - Requires Bearer token via `Authorization: Bearer <API_TOKEN>` header.
  - Request JSON:
    ```json
    {
      "organization_name_chinese": "後勤應用系統部",
      "ldap_username": "john.doe",
      "package_manager": "npm",
      "shared": false,
      "app_id": "my-app",
      "action": "create"
    }
    ```
  - See error and success response examples below.

- **POST /api/repository/batch** — Create or delete multiple repositories
  - Requires Bearer token via `Authorization: Bearer <API_TOKEN>` header.
  - Request JSON:
    ```json
    {
      "requests": [ ... ],
      "fail_fast": false,
      "max_requests": 50
    }
    ```

## 📝 Example Usage

- To create a repository:

  ```bash
  curl -X POST http://127.0.0.1:5000/api/repository \
    -H "Authorization: Bearer <API_TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{
      "organization_name_chinese": "後勤應用系統部",
      "ldap_username": "john.doe",
      "package_manager": "npm",
      "shared": false,
      "app_id": "my-app"
    }'
  ```

- To batch create/delete repositories, see the batch endpoint above.

### Batch Request Example

- **Request Body:**

  ```json
  {
    "requests": [
      {
        "organization_name_chinese": "後勤應用系統部",
        "ldap_username": "john.doe",
        "package_manager": "npm",
        "shared": false,
        "app_id": "frontend-app",
        "action": "create"
      },
      {
        "organization_name_chinese": "後勤應用系統部",
        "ldap_username": "jane.smith",
        "package_manager": "maven",
        "shared": true,
        "action": "delete"
      }
    ],
    "fail_fast": false,
    "max_requests": 50
  }
  ```

- **Success Response:**

  ```json
  {
    "success": true,
    "message": "Batch processing completed. 2/2 requests succeeded",
    "processed_count": 2,
    "total_requests": 2,
    "results": [
      {
        "index": 0,
        "success": true,
        "data": {
          "action": "create",
          "repository_name": "npm-release-frontend-app",
          "ldap_username": "john.doe",
          "organization_id": "org123",
          "package_manager": "npm"
        },
        "message": "Successfully created repository and privileges"
      },
      {
        "index": 1,
        "success": true,
        "data": {
          "action": "delete",
          "repository_name": "maven-release-shared",
          "ldap_username": "jane.smith",
          "organization_id": "org123",
          "package_manager": "maven"
        },
        "message": "Successfully deleted repository and privileges"
      }
    ],
    "errors": null
  }
  ```

- **Error Response (Partial Success):**
  ```json
  {
    "success": false,
    "message": "Batch processing completed. 1/2 requests succeeded",
    "processed_count": 1,
    "total_requests": 2,
    "results": [
      {
        "index": 0,
        "success": true,
        "data": {
          "action": "create",
          "repository_name": "npm-release-frontend-app",
          "ldap_username": "john.doe",
          "organization_id": "org123",
          "package_manager": "npm"
        },
        "message": "Successfully created repository and privileges"
      }
    ],
    "errors": [
      {
        "index": 1,
        "success": false,
        "error": "Field 'ldap_username' cannot be empty",
        "request": {
          "organization_name_chinese": "後勤應用系統部",
          "ldap_username": "",
          "package_manager": "maven",
          "shared": true,
          "action": "delete"
        }
      }
    ]
  }
  ```
