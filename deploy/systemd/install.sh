#!/usr/bin/env bash
# Install HPEO as a systemd service from the stick/project folder.  Usage: sudo deploy/systemd/install.sh
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
id hpeo >/dev/null 2>&1 || useradd --system --home /opt/hpeo --shell /usr/sbin/nologin hpeo
mkdir -p /opt/hpeo /var/lib/hpeo
cp -a "$SRC"/. /opt/hpeo/
rm -rf /opt/hpeo/state /opt/hpeo/.git
python3 -m venv /opt/hpeo/.venv
TAG="$(uname -s | tr A-Z a-z)-$(uname -m)"
if [ -d "/opt/hpeo/wheels/$TAG" ]; then
  /opt/hpeo/.venv/bin/pip install --no-index --find-links "/opt/hpeo/wheels/$TAG" -r /opt/hpeo/requirements-runtime.txt
else
  /opt/hpeo/.venv/bin/pip install -r /opt/hpeo/requirements-runtime.txt
fi
chown -R hpeo:hpeo /opt/hpeo /var/lib/hpeo
install -m 644 /opt/hpeo/deploy/systemd/hpeo.service /etc/systemd/system/hpeo.service
systemctl daemon-reload
echo "Installed. Run calibration as the service user first, then enable:"
echo "  sudo -u hpeo HPEO_STATE_DIR=/var/lib/hpeo /opt/hpeo/.venv/bin/python -m deploy doctor"
echo "  sudo systemctl enable --now hpeo"
