"""Pre-download wheels for offline installs from the USB stick.

    python deploy/make_bundle.py --python 3.12 --targets linux-x86_64 linux-aarch64 windows-amd64

Wheels are tied to the Python minor version, so build for the version(s) installed on the target machines.
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLATFORMS = {
    "linux-x86_64": ["manylinux2014_x86_64", "manylinux_2_28_x86_64"],
    "linux-aarch64": ["manylinux2014_aarch64", "manylinux_2_28_aarch64"],
    "windows-amd64": ["win_amd64"],
    "windows-arm64": ["win_arm64"],
    "darwin-arm64": ["macosx_11_0_arm64"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default="3.12", help="target Python minor version, e.g. 3.12")
    ap.add_argument("--targets", nargs="+", default=["linux-x86_64", "linux-aarch64", "windows-amd64"],
                    choices=PLATFORMS)
    a = ap.parse_args()
    for t in a.targets:
        out = os.path.join(ROOT, "wheels", t)
        os.makedirs(out, exist_ok=True)
        cmd = [sys.executable, "-m", "pip", "download", "-r", os.path.join(ROOT, "requirements-runtime.txt"),
               "-d", out, "--only-binary=:all:", "--python-version", a.python, "--implementation", "cp"]
        for p in PLATFORMS[t]:
            cmd += ["--platform", p]
        print(">>", t)
        subprocess.run(cmd, check=True)
    print("Done. Copy the whole project folder (including wheels/) to the USB stick.")


if __name__ == "__main__":
    main()
