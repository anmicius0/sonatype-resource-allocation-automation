#!/usr/bin/env python3
"""Unified Nexus Repository Manager automation tool.

This script provides both CLI and web interfaces for creating and deleting
Nexus repositories and managing user privileges. It combines the functionality
of app.py, main.py, and provides a unified entry point.

Usage:
    nexus-manager                   # Start web interface (default)
    nexus-manager web               # Start web interface
    nexus-manager cli create        # CLI: Create repository and privileges
    nexus-manager cli delete        # CLI: Delete repository and privileges
    nexus-manager --help            # Show help
"""

import sys
import os
import argparse
import webbrowser
import time
import threading
from flask import Flask, render_template, request, flash, redirect, url_for, session
from dotenv import load_dotenv

from nexus_manager.core import Config, PrivilegeManager, main as cli_main
from nexus_manager.utils import load_json_file, parse_bool, parse_csv

# Get the directory where the script/executable is located
if getattr(sys, "frozen", False):
    # If running as a packaged executable
    application_path = os.path.dirname(sys.executable)
else:
    # If running as a Python script
    application_path = os.path.dirname(os.path.abspath(__file__))

# Load .env file from the config directory
env_path = os.path.join(application_path, "config", ".env")
load_dotenv(env_path)

# Flask app setup
app = Flask(__name__, template_folder=os.path.join(application_path, "templates"))
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default-secret-key-change-me")


def load_configuration_data():
    """Load configuration data with error handling."""
    # Get shared package managers from environment variable
    shared_package_managers_env = os.getenv(
        "SHARED_PACKAGE_MANAGERS", "npm,maven2,nuget,yum,raw"
    )
    shared_package_managers = parse_csv(shared_package_managers_env)

    # Load organizations from config directory
    config_dir = os.path.join(application_path, "config")
    organizations = load_json_file(
        os.path.join(config_dir, "organisations.json"), default=[]
    )

    # Load package manager configuration
    pm_config = load_json_file(
        os.path.join(config_dir, "package_manager_config.json"),
        default={"supported_formats": {}},
    )
    supported_formats = pm_config.get("supported_formats", {})

    # Filter to only include supported proxy formats that have URLs
    package_managers = sorted(
        [
            pm
            for pm in supported_formats.keys()
            if supported_formats[pm].get("proxy_supported", False)
            and supported_formats[pm].get("default_url")
        ]
    )

    # Filter shared options to only supported formats
    shared_package_managers = [
        pm
        for pm in shared_package_managers
        if pm in supported_formats
        and supported_formats[pm].get("proxy_supported", False)
    ]

    return organizations, package_managers, shared_package_managers


@app.route("/set_language/<lang>")
def set_language(lang):
    if lang not in ["en-us", "zh-tw"]:
        lang = "en-us"
    session["lang"] = lang
    next_url = request.args.get("next") or url_for("index")
    return redirect(next_url)


def get_lang():
    return session.get("lang", "en-us")


@app.route("/")
def index():
    """Main form page for user input."""
    current_values = {
        "organization_id": os.getenv("ORGANIZATION_ID", ""),
        "ldap_username": os.getenv("LDAP_USERNAME", ""),
        "app_id": os.getenv("APP_ID", ""),
        "shared": parse_bool(os.getenv("SHARED", "false")),
        "package_manager": os.getenv(
            "PACKAGE_MANAGER", os.getenv("DEFAULT_PACKAGE_MANAGER", "apt")
        ),
    }

    organizations, package_managers, shared_package_managers = load_configuration_data()
    lang = get_lang()

    return render_template(
        "index.html",
        values=current_values,
        package_managers=package_managers,
        shared_package_managers=shared_package_managers,
        organizations=organizations,
        lang=lang,
    )


@app.route("/process", methods=["POST"])
def process_form():
    """Process the form submission and execute the repository operation."""
    try:
        # Get and validate form data
        organization_id = request.form.get("organization_id", "").strip()
        ldap_username = request.form.get("ldap_username", "").strip()
        app_id = request.form.get("app_id", "").strip()
        shared = request.form.get("shared") == "on"
        package_manager = request.form.get(
            "package_manager", os.getenv("DEFAULT_PACKAGE_MANAGER", "apt")
        )
        action = request.form.get("action", "create")
        lang = get_lang()

        # Basic validation
        if not organization_id:
            flash(
                {"en-us": "Organization ID is required", "zh-tw": "組織 ID 為必填項目"}[
                    lang
                ],
                "error",
            )
            return redirect(url_for("index"))

        if not ldap_username:
            flash(
                {"en-us": "LDAP Username is required", "zh-tw": "LDAP 帳號為必填項目"}[
                    lang
                ],
                "error",
            )
            return redirect(url_for("index"))

        if not shared and not app_id:
            flash(
                {
                    "en-us": "APP ID is required when not using shared repository",
                    "zh-tw": "未勾選共用倉庫時，APP ID 為必填項目",
                }[lang],
                "error",
            )
            return redirect(url_for("index"))

        # Set environment variables for config creation
        os.environ.update(
            {
                "ORGANIZATION_ID": organization_id,
                "LDAP_USERNAME": ldap_username,
                "APP_ID": app_id if app_id else "shared",
                "SHARED": "true" if shared else "false",
                "PACKAGE_MANAGER": package_manager,
            }
        )

        # Create config and run operation
        config = Config.from_env_and_action(action)
        manager = PrivilegeManager(config)

        # Prepare result data
        operation_result = {
            "action": action,
            "repository_name": config.repository_name,
            "ldap_username": config.ldap_username,
            "success": True,
            "message": {
                "en-us": f"Successfully {action}d repository and privileges.",
                "zh-tw": f"{('建立' if action == 'create' else '刪除')}倉庫與權限成功。",
            }[lang],
        }

        # Execute operation
        try:
            manager.run()
        except Exception as e:
            operation_result["success"] = False
            operation_result["message"] = str(e)

        return render_template("result.html", result=operation_result, lang=lang)

    except Exception as e:
        lang = get_lang()
        flash(
            {
                "en-us": f"❌ Configuration error: {str(e)}",
                "zh-tw": f"❌ 設定錯誤: {str(e)}",
            }[lang],
            "error",
        )
        return redirect(url_for("index"))


def open_browser(host, port):
    """Open browser after a short delay to ensure server is running."""
    time.sleep(1.5)
    webbrowser.open(f"http://{host}:{port}")


def run_web_interface():
    """Run the Flask web interface."""
    # Get configuration from environment variables
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    auto_open = os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true"

    print("🚀 Starting Nexus Repository Manager Web Interface...")
    print(f"📍 Server: http://{host}:{port}")
    print("💡 Press Ctrl+C to stop the server")

    if auto_open and host in ["127.0.0.1", "localhost", "0.0.0.0"]:
        # Open browser in a separate thread
        browser_thread = threading.Thread(
            target=open_browser, args=("127.0.0.1" if host == "0.0.0.0" else host, port)
        )
        browser_thread.daemon = True
        browser_thread.start()

    try:
        app.run(debug=debug, host=host, port=port, use_reloader=False)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)


def run_cli_interface(action):
    """Run the CLI interface with the specified action."""
    # Set up sys.argv for the CLI main function
    original_argv = sys.argv
    sys.argv = ["nexus-manager", action]

    try:
        cli_main()
    except SystemExit as e:
        # Handle normal exit codes from CLI
        sys.exit(e.code)
    except Exception as e:
        print(f"❌ CLI error: {e}")
        sys.exit(1)
    finally:
        # Restore original argv
        sys.argv = original_argv


def main():
    """Main entry point that handles both CLI and web interfaces."""
    parser = argparse.ArgumentParser(
        description="Nexus Repository Manager - Unified CLI and Web Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexus-manager                    # Start web interface (default)
  nexus-manager web               # Start web interface
  nexus-manager cli create        # CLI: Create repository and privileges
  nexus-manager cli delete        # CLI: Delete repository and privileges

Environment Variables:
  PORT                 # Web server port (default: 5000)
  FLASK_HOST           # Web server host (default: 127.0.0.1)
  AUTO_OPEN_BROWSER    # Auto-open browser (default: true)
  FLASK_DEBUG          # Enable debug mode (default: false)

Configuration:
  Place your .env file in the config/ directory with your Nexus settings.
        """,
    )

    parser.add_argument(
        "mode",
        nargs="?",
        choices=["web", "cli"],
        default="web",
        help="Interface mode: 'web' for web interface, 'cli' for command line (default: web)",
    )

    parser.add_argument(
        "action",
        nargs="?",
        choices=["create", "delete"],
        help="CLI action: 'create' or 'delete' (required when mode is 'cli')",
    )

    parser.add_argument(
        "--version", action="version", version="Nexus Repository Manager v1.0.0"
    )

    # Handle case where no arguments are provided (default to web)
    if len(sys.argv) == 1:
        run_web_interface()
        return

    args = parser.parse_args()

    if args.mode == "web":
        run_web_interface()
    elif args.mode == "cli":
        if not args.action:
            parser.error("CLI mode requires an action: 'create' or 'delete'")
        run_cli_interface(args.action)


if __name__ == "__main__":
    main()
