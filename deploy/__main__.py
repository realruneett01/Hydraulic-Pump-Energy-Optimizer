"""HPEO deployment CLI:  python -m deploy {detect|configure|calibrate|doctor|start}"""

import argparse
import asyncio
import json
import logging
import sys

from deploy import hardware
from deploy.calibrate import preflight
from deploy.config import auto_configure, load_config, load_profile, save_profile

ICON = {"PASS": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}


def print_report(rep) -> None:
    for c in rep["checks"]:
        print(f"{ICON[c['status']]} {c['name']:<22} {c['detail']}")
    verdict = "READY FOR LIVE DEPLOYMENT" if rep.get("live_ready") else (
        "PASSED (simulation/no live sensors only - NOT deployable)" if rep["ok"] else "NOT READY - see FAIL items")
    print(f"\nVerdict: {verdict}")


def cmd_detect(a):
    print(json.dumps({"host": hardware.host_info(), "serial_ports": hardware.list_serial_ports()}, indent=2))
    return 0


def cmd_configure(a):
    r = auto_configure(a.opcua, a.serial_port, a.simulate)
    print(json.dumps(r["report"], indent=2))
    return 0


def cmd_doctor(a):
    """Configure-if-needed, calibrate, run every check, and seal the result for `start`."""
    cfg = load_config()
    rep = preflight(cfg)
    print_report(rep)
    if rep["ok"]:
        path = save_profile({"sensor": rep["sensor"], "pump_csv_sha256": rep["pump_csv_sha256"],
                             "mode": cfg["mode"], "live_ready": rep["live_ready"], "host": rep["host"]})
        print(f"Calibration profile written: {path}")
    return 0 if rep["ok"] else 1


def cmd_start(a):
    from deploy.calibrate import PUMP_CSV
    from deploy.config import file_sha256
    cfg = load_config()
    prof = load_profile()
    if (prof is None or prof.get("pump_csv_sha256") != file_sha256(PUMP_CSV) or prof.get("host") != hardware.host_info()
            or prof.get("mode") != cfg["mode"]):
        print("No valid calibration for this machine/config - running calibration first...\n")
        if cmd_doctor(a) != 0:
            print("Refusing to start: pre-flight failed.")
            return 2
        prof = load_profile()
    if not prof["live_ready"] and not a.allow_simulation:
        print("Refusing to start: no live sensors verified. Use --allow-simulation for a demo.")
        return 3
    from deploy.runtime import run
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        asyncio.run(run(cfg, prof))
    except KeyboardInterrupt:
        pass
    return 0


def main():
    ap = argparse.ArgumentParser(prog="python -m deploy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect").set_defaults(fn=cmd_detect)
    c = sub.add_parser("configure")
    c.add_argument("--opcua", help="PLC OPC-UA endpoint to probe, e.g. opc.tcp://192.168.0.10:4840")
    c.add_argument("--serial-port")
    c.add_argument("--simulate", action="store_true")
    c.set_defaults(fn=cmd_configure)
    sub.add_parser("doctor", aliases=["calibrate"]).set_defaults(fn=cmd_doctor)
    s = sub.add_parser("start")
    s.add_argument("--allow-simulation", action="store_true")
    s.set_defaults(fn=cmd_start)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
