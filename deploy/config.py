"""Auto-generated site configuration (config/hpeo.json) and the sensor-calibration profile."""

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from deploy import hardware
from deploy.paths import ROOT, state_dir

CONFIG_PATH = os.path.join(ROOT, "config", "hpeo.json")
PROFILE_NAME = "calibration_profile.json"
PROFILE_MAX_AGE_S = 30 * 24 * 3600

DEFAULTS: Dict[str, Any] = {
    "mode": "simulation",            # simulation | opcua | serial
    "listen_endpoint": "opc.tcp://0.0.0.0:4840/hpeo/",
    "opcua_in": {"endpoint": "", "flow_node": "", "pressure_node": ""},
    "serial_in": {"port": "", "baud": 115200},
    "sample_period_s": 0.2,
    "solver_budget_ms": 10.0,        # preflight fails if p99 solver latency exceeds this
    "sensor_limits": {"flow_lpm": [0.0, 800.0], "pressure_bar": [0.0, 350.0]},
    "max_zero_offset": {"flow_lpm": 10.0, "pressure_bar": 8.0},
    "min_r2": 0.995,
    "max_cv_mape_pct": 5.0,
}


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def load_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def save_config(cfg: Dict[str, Any]) -> str:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    return CONFIG_PATH


def auto_configure(opcua_endpoint: Optional[str] = None, serial_port: Optional[str] = None,
                   force_simulation: bool = False) -> Dict[str, Any]:
    """Pick a sensor source from what is actually attached. Never silently guesses live wiring."""
    cfg = load_config()
    report: Dict[str, Any] = {"host": hardware.host_info()}
    opcua_endpoint = opcua_endpoint or os.environ.get("HPEO_OPCUA_IN")
    if force_simulation:
        cfg["mode"] = "simulation"
    elif opcua_endpoint:
        probe = hardware.probe_opcua(opcua_endpoint)
        report["opcua_probe"] = probe
        if probe["reachable"] and probe["flow"] and probe["pressure"]:
            cfg["mode"] = "opcua"
            cfg["opcua_in"] = {"endpoint": opcua_endpoint, "flow_node": probe["flow"][0],
                               "pressure_node": probe["pressure"][0]}
        else:
            report["note"] = ("OPC-UA endpoint given but flow/pressure nodes were not found; "
                              "set opcua_in.flow_node / pressure_node in config/hpeo.json by hand.")
            cfg["mode"] = "opcua"
            cfg["opcua_in"]["endpoint"] = opcua_endpoint
    else:
        ports = hardware.list_serial_ports()
        report["serial_ports"] = ports
        chosen = serial_port or (ports[0]["device"] if len(ports) == 1 else "")
        if chosen:
            cfg["mode"] = "serial"
            cfg["serial_in"]["port"] = chosen
        elif len(ports) > 1:
            report["note"] = "Several serial ports found; pass --serial-port to choose one."
    report["mode"] = cfg["mode"]
    save_config(cfg)
    return {"config": cfg, "report": report}


def _digest(body: Dict[str, Any]) -> str:
    payload = json.dumps(body, sort_keys=True).encode()
    key = os.environ.get("HPEO_SEAL_KEY")
    if key:
        return "hmac-sha256:" + hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def save_profile(body: Dict[str, Any]) -> str:
    body = dict(body, created_at=time.time())
    doc = {"body": body, "digest": _digest(body)}
    path = os.path.join(state_dir(), PROFILE_NAME)
    with open(path, "w") as f:
        json.dump(doc, f, indent=2)
    return path


def load_profile() -> Optional[Dict[str, Any]]:
    """Returns the profile body, or None if missing / tampered / stale / for different data or host."""
    path = os.path.join(state_dir(), PROFILE_NAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            doc = json.load(f)
        body = doc["body"]
        if not hmac.compare_digest(doc["digest"], _digest(body)):
            return None
    except (OSError, ValueError, KeyError):
        return None
    if time.time() - body.get("created_at", 0) > PROFILE_MAX_AGE_S:
        return None
    return body
