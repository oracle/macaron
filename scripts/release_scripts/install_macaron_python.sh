#!/bin/bash

# Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
set -euo pipefail

print_help() {
cat << EOF
Usage: $0 <MACARON_VERSION> [--install-slsa-verifier] [-h|--help]

Arguments:
  <MACARON_VERSION>           Version of Macaron to install.
  --install-slsa-verifier     (Optional) Install the SLSA Verifier binary.
  -h, --help                  Show this help and exit.

Examples:
  $0 0.21.0
  $0 0.21.0 --install-slsa-verifier
EOF
}

# SLSA Verifier Installer
# Get the checksum from https://github.com/slsa-framework/slsa-verifier/blob/main/SHA256SUM.md.
install_slsa_verifier() {
    SLSA_VERIFIER_TAG="v2.7.1"
    SLSA_VERIFIER_BIN="slsa-verifier-linux-amd64"
    SLSA_VERIFIER_BIN_PATH="${HOME}/.local/bin"
    SLSA_VERIFIER_CHECKSUM="946dbec729094195e88ef78e1734324a27869f03e2c6bd2f61cbc06bd5350339"

    if ! command -v slsa-verifier >/dev/null 2>&1; then
        echo "[Info] Installing slsa-verifier..."
        mkdir -p "$SLSA_VERIFIER_BIN_PATH"
        curl --fail -L -o "${SLSA_VERIFIER_BIN_PATH}/slsa-verifier" "https://github.com/slsa-framework/slsa-verifier/releases/download/${SLSA_VERIFIER_TAG}/${SLSA_VERIFIER_BIN}"
        SLSA_VERIFIER_COMPUTED_HASH=$(sha256sum "${SLSA_VERIFIER_BIN_PATH}/slsa-verifier" | cut -d' ' -f1)
        if [ "$SLSA_VERIFIER_COMPUTED_HASH" != "$SLSA_VERIFIER_CHECKSUM" ]; then
            echo "[Error] SLSA verification did not pass. Removing slsa-verifier binary and exiting." >&2
            rm -f "${SLSA_VERIFIER_BIN_PATH}/slsa-verifier"
            exit 1
        fi
        chmod +x "${SLSA_VERIFIER_BIN_PATH}/slsa-verifier"
        echo "[Info] slsa-verifier installed at: ${SLSA_VERIFIER_BIN_PATH}/slsa-verifier"
    else
        echo "[Info] slsa-verifier already installed."
    fi
}

# Handle arguments.
INSTALL_SLSA=0
MACARON_VERSION=""

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      print_help
      exit 0
      ;;
    --install-slsa-verifier)
      INSTALL_SLSA=1
      ;;
    *)
      if [[ -z "$MACARON_VERSION" ]]; then
        MACARON_VERSION="$arg"
      fi
      ;;
  esac
done

if [[ -z "$MACARON_VERSION" ]]; then
  echo "Error: Please provide the Macaron version as an argument."
  print_help
  exit 1
fi

if [[ "$INSTALL_SLSA" -eq 1 ]]; then
  install_slsa_verifier
fi

# Macaron Installer

# Configuration.
PYTHON_VERSION="3"
MACARON_DISTRO="py3-none-linux_x86_64"
MACARON_WHEEL="macaron-${MACARON_VERSION}-${MACARON_DISTRO}.whl"
MACARON_REQUIREMENTS="macaron-${MACARON_VERSION}-${MACARON_DISTRO}-requirements.txt"
MACARON_REPO="https://github.com/oracle/macaron"
VENV_DIR=".venv"

echo "Using Macaron version: $MACARON_VERSION"

# Download Macaron release assets if not already downloaded.
echo "Checking for release files..."
if [[ ! -f "$MACARON_WHEEL" ]]; then
  echo "Downloading wheel: $MACARON_WHEEL"
  wget "${MACARON_REPO}/releases/download/v${MACARON_VERSION}/${MACARON_WHEEL}"
else
  echo "Using existing wheel: $MACARON_WHEEL"
fi

if [[ ! -f "$MACARON_REQUIREMENTS" ]]; then
  echo "Downloading requirements: $MACARON_REQUIREMENTS"
  wget "${MACARON_REPO}/releases/download/v${MACARON_VERSION}/${MACARON_REQUIREMENTS}"
else
  echo "Using existing requirements: $MACARON_REQUIREMENTS"
fi

# Set up Python virtual environment.
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment with Python ${PYTHON_VERSION}..."
  python${PYTHON_VERSION} -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
export PATH="${VENV_DIR}/bin:$PATH"

# Install Macaron package and dependencies.
echo "Installing Macaron..."
pip install --no-deps "${MACARON_WHEEL}"
pip install --no-deps -r "${MACARON_REQUIREMENTS}"

# Check version.
echo "Macaron successfully installed:"
macaron --version
