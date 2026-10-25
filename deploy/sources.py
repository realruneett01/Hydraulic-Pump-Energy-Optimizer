"""Sensor sources feeding (flow L/min, pressure bar) to the optimizer."""

import asyncio
import time
from typing import Tuple


class SensorError(RuntimeError):
    pass


class SimulationSource:
    """Replays the physics-based press cycle simulator. NOT a real sensor; flagged as such everywhere."""
    live = False

    def __init__(self, dt: float = 0.2):
        from simulator.press_demand import PressCycleSimulator
        df = PressCycleSimulator(dt_seconds=dt, seed=42).simulate_fleet_demand(num_cycles=3)
        self._rows = list(zip(df["target_flow_lpm"], df["target_pressure_bar"]))
        self._i = 0

    async def open(self): ...
    async def close(self): ...

    async def read(self) -> Tuple[float, float]:
        q, p = self._rows[self._i % len(self._rows)]
        self._i += 1
        return float(q), float(p)


class OpcUaSource:
    live = True

    def __init__(self, endpoint: str, flow_node: str, pressure_node: str):
        self.endpoint, self.flow_node, self.pressure_node = endpoint, flow_node, pressure_node
        self._client = None

    async def open(self):
        from asyncua import Client
        if not (self.endpoint and self.flow_node and self.pressure_node):
            raise SensorError("opcua_in.endpoint/flow_node/pressure_node not configured")
        self._client = Client(self.endpoint, timeout=3)
        await self._client.connect()
        self._q = self._client.get_node(self.flow_node)
        self._p = self._client.get_node(self.pressure_node)

    async def close(self):
        if self._client:
            await self._client.disconnect()

    async def read(self) -> Tuple[float, float]:
        try:
            return float(await self._q.read_value()), float(await self._p.read_value())
        except Exception as e:  # noqa: BLE001
            raise SensorError(f"OPC-UA read failed: {e}") from e


class SerialSource:
    """Generic ASCII line protocol: one 'flow_lpm,pressure_bar' line per sample."""
    live = True

    def __init__(self, port: str, baud: int = 115200):
        self.port, self.baud = port, baud
        self._ser = None

    async def open(self):
        import serial
        if not self.port:
            raise SensorError("serial_in.port not configured")
        self._ser = serial.Serial(self.port, self.baud, timeout=1.0)

    async def close(self):
        if self._ser:
            self._ser.close()

    def _read_line(self) -> Tuple[float, float]:
        raw = self._ser.readline().decode("ascii", "replace").strip()
        parts = raw.split(",")
        if len(parts) != 2:
            raise SensorError(f"unparseable serial line: {raw!r}")
        return float(parts[0]), float(parts[1])

    async def read(self) -> Tuple[float, float]:
        try:
            return await asyncio.get_running_loop().run_in_executor(None, self._read_line)
        except (ValueError, OSError) as e:
            raise SensorError(str(e)) from e


def make_source(cfg) -> object:
    mode = cfg["mode"]
    if mode == "opcua":
        c = cfg["opcua_in"]
        return OpcUaSource(c["endpoint"], c["flow_node"], c["pressure_node"])
    if mode == "serial":
        return SerialSource(cfg["serial_in"]["port"], cfg["serial_in"]["baud"])
    return SimulationSource(cfg["sample_period_s"])


async def sample(source, n: int, period: float):
    out, t0 = [], time.monotonic()
    for _ in range(n):
        out.append(await source.read())
        await asyncio.sleep(period)
    return out, time.monotonic() - t0
