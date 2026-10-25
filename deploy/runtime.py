"""Live supervisory loop: sensors -> optimizer -> OPC-UA setpoint publication (advisory, Level 2)."""

import asyncio
import logging
import time

from asyncua import Server, ua

from deploy.sources import SensorError, make_source

log = logging.getLogger("hpeo")
MAX_CONSECUTIVE_FAULTS = 3


async def run(cfg, profile) -> None:
    from optimizer.optimizer import PumpStagingOptimizer
    opt = PumpStagingOptimizer()
    off = profile["sensor"]["offsets"]
    lim = cfg["sensor_limits"]
    src = make_source(cfg)
    await src.open()

    server = Server()
    await server.init()
    server.set_endpoint(cfg["listen_endpoint"])
    server.set_server_name("HPEO Supervisory Optimizer")
    ns = await server.register_namespace("urn:hpeo:supervisor")
    root = await server.nodes.objects.add_folder(ns, "HPEO_Press_HPU")
    tel = await root.add_folder(ns, "PressTelemetry")
    n_flow = await tel.add_variable(ns, "DemandFlow_LPM", 0.0, ua.VariantType.Float)
    n_pres = await tel.add_variable(ns, "DemandPressure_Bar", 0.0, ua.VariantType.Float)
    sp = await root.add_folder(ns, "PumpSetpoints")
    n_code = await sp.add_variable(ns, "StagingCode", "STARTING", ua.VariantType.String)
    n_power = await sp.add_variable(ns, "OptimizedPower_KW", 0.0, ua.VariantType.Float)
    sys_f = await root.add_folder(ns, "System")
    n_ok = await sys_f.add_variable(ns, "SensorsHealthy", False, ua.VariantType.Boolean)
    n_sim = await sys_f.add_variable(ns, "IsSimulation", not src.live, ua.VariantType.Boolean)
    n_hb = await sys_f.add_variable(ns, "Heartbeat", 0, ua.VariantType.Int64)
    pumps = {}
    for pid in opt.pump_ids:
        f = await sp.add_folder(ns, pid)
        pumps[pid] = (await f.add_variable(ns, f"{pid}_Active", False, ua.VariantType.Boolean),
                      await f.add_variable(ns, f"{pid}_DisplacementPct", 0.0, ua.VariantType.Float))

    faults = 0
    async with server:
        log.info("HPEO online on %s (mode=%s, simulation=%s)", cfg["listen_endpoint"], cfg["mode"], not src.live)
        while True:
            t0 = time.monotonic()
            try:
                q, p = await src.read()
                q, p = q - off["flow_lpm"], p - off["pressure_bar"]
                if not (lim["flow_lpm"][0] - 1 <= q <= lim["flow_lpm"][1] and lim["pressure_bar"][0] - 1 <= p <= lim["pressure_bar"][1]):
                    raise SensorError(f"out of range: Q={q:.1f} P={p:.1f}")
                faults = 0
                d = opt.optimize_step(max(0.0, q), max(0.0, p))
                await n_flow.write_value(float(q), ua.VariantType.Float)
                await n_pres.write_value(float(p), ua.VariantType.Float)
                await n_code.write_value(d.staging_code, ua.VariantType.String)
                await n_power.write_value(float(d.total_power_kw), ua.VariantType.Float)
                for pid, (a, disp) in pumps.items():
                    await a.write_value(bool(d.active_pumps[pid]), ua.VariantType.Boolean)
                    await disp.write_value(float(d.displacements[pid] * 100), ua.VariantType.Float)
                await n_ok.write_value(True, ua.VariantType.Boolean)
            except SensorError as e:
                faults += 1
                log.warning("sensor fault %d/%d: %s", faults, MAX_CONSECUTIVE_FAULTS, e)
                if faults >= MAX_CONSECUTIVE_FAULTS:
                    # Advisory output is withdrawn; the PLC must fall back to its own native staging.
                    await n_ok.write_value(False, ua.VariantType.Boolean)
                    await n_code.write_value("SENSOR_FAULT_PLC_AUTHORITY", ua.VariantType.String)
            await n_hb.write_value(int(time.time()), ua.VariantType.Int64)
            await asyncio.sleep(max(0.0, cfg["sample_period_s"] - (time.monotonic() - t0)))
