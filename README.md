# Nexus Manager

## Overview

Nexus Manager is a cross-platform tool for managing Nexus Repository and IQ Server, providing both a web interface and a CLI. It is distributed as a standalone executable for Windows, macOS, and Linux—no Python installation required.

---

## Using the Release Executable

### 1. Download & Extract

- Download the appropriate archive for your platform from the release page.
- Extract the archive. You will get a folder containing:
  - The executable (`nexus-manager` or `nexus-manager.exe`)
  - `config/` (configuration files)
  - `templates/` (web UI templates)
  - `pyproject.toml`
  - `README.md`

### 2. Configure Environment

- Copy `config/.env.example` to `config/.env` and fill in your server details and secrets.

### 3. Run the Application

- **Web UI:**
  - On Linux/macOS: `./nexus-manager`
  - On Windows: `nexus-manager.exe`
- **CLI:**
  - On Linux/macOS: `./nexus-manager cli`
  - On Windows: `nexus-manager.exe cli`

---

## Customization

### Configuration

- All configuration is in the `config/` directory.
- Edit `config/.env` for environment variables (see `.env.example` for options).
- Edit `config/organisations.json` and `config/package_manager_config.json` for organization and package manager settings.

### Web Templates

- The web UI uses Jinja2 templates in the `templates/` directory.
- Customize `index.html` and `result.html` as needed.

---

## Codebase Maintenance

### Structure

- `nexus_manager.py`: Main entry point.
- `nexus_manager/`: Core logic and utilities.
  - `core.py`: Main business logic.
  - `utils.py`: Helper functions.
  - `error_handler.py`: Error handling.
- `config/`: Configuration files.
- `templates/`: Web UI templates.

### Adding Features

- Add new logic in `nexus_manager/` as needed.
- Register new CLI commands or web routes in `nexus_manager.py` or `core.py`.
- Update templates for UI changes.

### Dependency Management

- Dependencies are managed with [uv](https://github.com/astral-sh/uv) and listed in `pyproject.toml`.
- To add a dependency:
  1. Install [uv](https://github.com/astral-sh/uv) locally.
  2. Run `uv pip install <package>`.
  3. Update `pyproject.toml` and commit changes.

### Building the Executable

- Builds are automated via GitHub Actions.
- To build locally:
  1. Install [uv](https://github.com/astral-sh/uv) and [pyinstaller](https://pyinstaller.org/).
  2. Run the build command as in `.github/workflows/build-release.yml`.

---

## Support

- For issues, open a GitHub issue in this repository.
- For configuration help, see comments in `config/.env.example`.

---

## License

See `LICENSE` file (if present) for license information.
