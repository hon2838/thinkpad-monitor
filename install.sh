#!/usr/bin/env bash
# User-local install, no root and no modification of system Python.
set -euo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT_DIR}/scripts/install.sh" "$@"
