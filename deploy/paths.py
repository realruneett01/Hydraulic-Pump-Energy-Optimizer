"""Locates the portable install root and writable state directory (works from a USB stick)."""

import os
import platform
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def state_dir() -> str:
    """Writable dir for calibration profile + logs. Prefers <root>/state; falls back if read-only media."""
    override = os.environ.get("HPEO_STATE_DIR")
    candidates = [override] if override else []
    candidates += [os.path.join(ROOT, "state"),
                   os.path.join(os.path.expanduser("~"), ".hpeo", "state"),
                   os.path.join(tempfile.gettempdir(), "hpeo-state")]
    for c in candidates:
        if not c:
            continue
        try:
            os.makedirs(c, exist_ok=True)
            probe = os.path.join(c, ".w")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return c
        except OSError:
            continue
    raise RuntimeError("No writable state directory available")


def platform_tag() -> str:
    m = platform.machine().lower()
    arch = {"amd64": "x86_64", "x64": "x86_64", "arm64": "aarch64"}.get(m, m)
    return f"{platform.system().lower()}-{arch}"
