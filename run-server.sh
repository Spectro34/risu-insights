#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${RISU_VENV:-.venv}"

if [[ "${VENV_PATH}" = /* ]]; then
  VENV_DIR="${VENV_PATH}"
else
  VENV_DIR="${SCRIPT_DIR}/${VENV_PATH}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  cat <<'EOF' >&2
Virtual environment not found.
Create one with:
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
or set RISU_VENV to a custom path before running this script.
EOF
  exit 1
fi

cd "${SCRIPT_DIR}"
# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
exec python3 server.py "$@"
