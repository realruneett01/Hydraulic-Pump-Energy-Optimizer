"""Deployment toolkit tests: auto-detection of a PLC's OPC-UA nodes and the calibration gate."""

import asyncio
import threading
import time

import pytest
from asyncua import Server

from deploy import config as dcfg
from deploy.calibrate import preflight


def _serve(flow, pressure, port, ready, stop, jitter=True):
    async def main():
        s = Server()
        await s.init()
        s.set_endpoint(f"opc.tcp://127.0.0.1:{port}/plc/")
        ns = await s.register_namespace("urn:fake:plc")
        f = await s.nodes.objects.add_folder(ns, "Press")
        nq = await f.add_variable(ns, "Main_Flow_LPM", flow)
        npr = await f.add_variable(ns, "System_Pressure_Bar", pressure)
        async with s:
            ready.set()
            k = 0
            while not stop.is_set():
                k += 1
                if jitter:  # real transducers always show noise; a perfectly flat line means a dead sensor
                    await nq.write_value(flow + 0.1 * (k % 5 - 2))
                    await npr.write_value(pressure + 0.05 * (k % 7 - 3))
                await asyncio.sleep(0.05)
    asyncio.run(main())


@pytest.fixture
def plc(request, tmp_path, monkeypatch):
    monkeypatch.setenv("HPEO_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(dcfg, "CONFIG_PATH", str(tmp_path / "hpeo.json"))
    flow, pressure, port = request.param
    jitter = port != 48403
    ready, stop = threading.Event(), threading.Event()
    t = threading.Thread(target=_serve, args=(flow, pressure, port, ready, stop, jitter), daemon=True)
    t.start()
    assert ready.wait(10)
    yield f"opc.tcp://127.0.0.1:{port}/plc/"
    stop.set()
    t.join(5)


@pytest.mark.parametrize("plc", [(1.5, 2.0, 48401)], indirect=True)
def test_idle_plc_is_autodetected_and_calibrated(plc):
    r = dcfg.auto_configure(opcua_endpoint=plc)
    assert r["config"]["mode"] == "opcua"
    assert r["report"]["opcua_probe"]["flow"] and r["report"]["opcua_probe"]["pressure"]
    assert r["config"]["opcua_in"]["flow_node"] != r["config"]["opcua_in"]["pressure_node"]
    cfg = dcfg.load_config()
    cfg["listen_endpoint"] = "opc.tcp://0.0.0.0:48499/hpeo/"
    rep = preflight(cfg)
    assert rep["ok"] and rep["live_ready"], rep["checks"]
    assert rep["sensor"]["offsets"]["flow_lpm"] == pytest.approx(1.5)


@pytest.mark.parametrize("plc", [(1.5, 120.0, 48402)], indirect=True)
def test_non_idle_pressure_fails_calibration(plc):
    dcfg.auto_configure(opcua_endpoint=plc)
    cfg = dcfg.load_config()
    cfg["listen_endpoint"] = "opc.tcp://0.0.0.0:48498/hpeo/"
    rep = preflight(cfg)
    assert not rep["ok"]
    assert any(c["name"] == "sensors:zero_pressure" and c["status"] == "FAIL" for c in rep["checks"])


@pytest.mark.parametrize("plc", [(0.0, 0.0, 48403)], indirect=True)
def test_frozen_sensors_are_rejected(plc):
    dcfg.auto_configure(opcua_endpoint=plc)
    cfg = dcfg.load_config()
    cfg["listen_endpoint"] = "opc.tcp://0.0.0.0:48497/hpeo/"
    rep = preflight(cfg)
    assert any(c["name"] == "sensors:alive" and c["status"] == "FAIL" for c in rep["checks"])


def test_tampered_profile_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HPEO_STATE_DIR", str(tmp_path))
    path = dcfg.save_profile({"mode": "opcua", "live_ready": True})
    assert dcfg.load_profile()["live_ready"] is True
    txt = open(path).read().replace('"live_ready": true', '"live_ready": false')
    open(path, "w").write(txt)
    assert dcfg.load_profile() is None
