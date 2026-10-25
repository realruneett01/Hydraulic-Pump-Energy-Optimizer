#!/usr/bin/env bash
# Portable launcher (Linux/macOS, x86_64 + ARM). Run straight from a USB stick:  ./start_hpeo.sh [doctor|detect|configure ...|start ...]
# The Python environment lives on the LOCAL disk (USB media is often noexec / FAT, which breaks venvs);
# application code and offline wheels are read from the stick.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python >= 3.10 not found. Install it (apt install python3 python3-venv) and re-run." >&2; exit 10; }

TAG="$(uname -s | tr A-Z a-z)-$(uname -m)"
VENV="${HPEO_VENV:-$HOME/.hpeo/venv-$TAG}"
STAMP="$VENV/.req-$(sha256sum requirements-runtime.txt 2>/dev/null | cut -c1-16 || shasum -a 256 requirements-runtime.txt | cut -c1-16)"

if [ ! -f "$STAMP" ]; then
  echo ">> Preparing environment in $VENV"
  "$PY" -m venv "$VENV" || { echo "venv creation failed (apt install python3-venv?)" >&2; exit 11; }
  if [ -d "wheels/$TAG" ]; then
    echo ">> Installing from offline wheels on the stick (wheels/$TAG)"
    "$VENV/bin/pip" install --no-index --find-links "wheels/$TAG" -r requirements-runtime.txt
  else
    echo ">> No offline wheels for $TAG; installing from the internet (see deploy/make_bundle.py to prebuild them)"
    "$VENV/bin/pip" install -r requirements-runtime.txt
  fi
  touch "$STAMP"
fi

[ $# -gt 0 ] || set -- start
exec "$VENV/bin/python" -m deploy "$@"
