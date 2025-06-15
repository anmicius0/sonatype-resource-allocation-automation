#!/bin/bash

# Simple build script for Nexus Repository Manager (macOS)
set -e

echo "🔨 Building Nexus Repository Manager..."

# Install dependencies using uv
echo "📦 Installing dependencies with uv..."
uv sync

# Clean previous builds
rm -rf dist/ build/ nexus-manager.spec

# Build executable
echo "🔧 Building executable with PyInstaller..."
uv run pyinstaller \
  --onefile \
  --name nexus-manager \
  --add-data config:config \
  --add-data nexus_manager:nexus_manager \
  --add-data templates:templates \
  --hidden-import=nexus_manager.core \
  --hidden-import=nexus_manager.utils \
  --hidden-import=nexus_manager.error_handler \
  --hidden-import=flask \
  --hidden-import=dotenv \
  --clean \
  nexus_manager.py

# Move executable to root directory
mv dist/nexus-manager ./nexus-manager

# Clean up
rm -rf dist/ build/ nexus-manager.spec
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo "✅ Build complete!"
echo "📦 Executable: ./nexus-manager"
echo ""
echo "Usage:"
echo "  ./nexus-manager              # Start web interface"
echo "  ./nexus-manager web         # Start web interface"
echo "  ./nexus-manager cli create  # CLI create"
echo "  ./nexus-manager cli delete  # CLI delete"
echo ""
