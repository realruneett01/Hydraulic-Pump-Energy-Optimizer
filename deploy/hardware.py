"""Auto-discovery of the machine and attached sensor interfaces (no network scanning)."""

import asyncio
import glob
import platform
import re
import sys
from typing import Any, Dict, List

FLOW_HINT = re.compile(r"flow|q_|lpm|l_min", re.I)
PRESSURE_HINT = re.compile(r"press|bar|p_sys|psi", re.I)


def host_info() -> Dict[str, Any]:
    return {"os": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": sys.version.split()[0]}


def list_serial_ports() -> List[Dict[str, str]]:
    """USB/serial DAQ adapters. Uses pyserial if present, else globs common device paths."""
    try:
        from serial.tools import list_ports
        return [{"device": p.device, "desc": p.description, "hwid": p.hwid}
                for p in list_ports.comports()]
    except ImportError:
        devs = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/cu.usb*")
        return [{"device": d, "desc": "unknown (pyserial not installed)", "hwid": ""} for d in devs]


async def _browse_candidates(endpoint: str, timeout: float) -> Dict[str, Any]:
    from asyncua import Client
    out: Dict[str, Any] = {"endpoint": endpoint, "reachable": False, "flow": [], "pressure": []}
    client = Client(endpoint, timeout=timeout)
    try:
        await client.connect()
        out["reachable"] = True
        stack = [(client.nodes.objects, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > 6:
                continue
            for child in await node.get_children():
                bn = (await child.read_browse_name()).Name
                cls = await child.read_node_class()
                if cls.name == "Variable":
                    if FLOW_HINT.search(bn):
                        out["flow"].append(child.nodeid.to_string())
                    if PRESSURE_HINT.search(bn):
                        out["pressure"].append(child.nodeid.to_string())
                else:
                    stack.append((child, depth + 1))
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return out


def probe_opcua(endpoint: str, timeout: float = 3.0) -> Dict[str, Any]:
    """Connect to a PLC/gateway OPC-UA endpoint and guess which nodes carry flow and pressure."""
    return asyncio.run(_browse_candidates(endpoint, timeout))
