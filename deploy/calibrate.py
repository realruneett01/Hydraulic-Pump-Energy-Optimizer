"""Calibration (model validation + sensor zero/range/noise) and the pre-flight gate."""

import asyncio
import json
import math
import os
import socket
import time
from typing import Any, Dict, List

import numpy as np

from deploy import hardware
from deploy.config import file_sha256
from deploy.paths import ROOT, state_dir
from deploy.sources import SensorError, make_source, sample

PUMP_CSV = os.path.join(ROOT, "data", "raw_pump_curves.csv")
TARIFF_META = os.path.join(ROOT, "data", "electricity_prices_es.meta.json")


def check(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail}  # status: PASS | WARN | FAIL


def model_validation(cfg) -> List[Dict[str, str]]:
    """In-sample R^2 plus leave-one-pressure-out MAPE, so the quoted error is not self-graded."""
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import PolynomialFeatures
    from pumps.pump_model import PumpFleetModel

    fleet = PumpFleetModel()
    res = []
    for pid, pump in fleet.pumps.items():
        d = pump.raw_data
        d = d[d["flow_lpm"] > 0]
        pred = np.array([pump.predict_power(q, p) for q, p in zip(d.flow_lpm, d.pressure_bar)])
        y = d.shaft_power_kw.values
        r2 = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        errs = []
        for p_out in d.pressure_bar.unique():
            tr, te = d[d.pressure_bar != p_out], d[d.pressure_bar == p_out]
            if len(tr) < 8:
                continue
            poly = PolynomialFeatures(2)
            m = Ridge(alpha=1e-3).fit(poly.fit_transform(tr[["flow_lpm", "pressure_bar"]].values),
                                      tr.shaft_power_kw.values)
            yp = m.predict(poly.transform(te[["flow_lpm", "pressure_bar"]].values))
            errs += list(np.abs(yp - te.shaft_power_kw.values) / te.shaft_power_kw.values * 100)
        cv = float(np.mean(errs)) if errs else math.nan
        ok = r2 >= cfg["min_r2"] and not math.isnan(cv) and cv <= cfg["max_cv_mape_pct"]
        res.append(check(f"model:{pid}", "PASS" if ok else "FAIL",
                         f"{pump.manufacturer} {pump.model_name}: R2={r2:.5f}, "
                         f"leave-one-pressure-out MAPE={cv:.2f}% (limits R2>={cfg['min_r2']}, "
                         f"MAPE<={cfg['max_cv_mape_pct']}%)"))
    return res


def solver_check(cfg) -> List[Dict[str, str]]:
    from optimizer.optimizer import PumpStagingOptimizer
    opt = PumpStagingOptimizer()
    max_q = sum(p.max_flow_lpm for p in opt.fleet.pumps.values())
    lat, bad = [], 0
    for q in np.linspace(5, max_q * 0.98, 60):
        for p in (50.0, 150.0, 260.0):
            t = time.perf_counter()
            d = opt.optimize_step(float(q), p)
            lat.append((time.perf_counter() - t) * 1e3)
            if not d.feasible or d.delivered_flow_lpm + 1e-6 < q - 0.01:
                bad += 1
    p99 = float(np.percentile(lat, 99))
    return [check("solver:feasibility", "PASS" if bad == 0 else "FAIL",
                  f"{bad} of {len(lat)} demand points unsatisfied"),
            check("solver:latency", "PASS" if p99 <= cfg["solver_budget_ms"] else "FAIL",
                  f"mean={np.mean(lat):.2f} ms, p99={p99:.2f} ms on this host (budget {cfg['solver_budget_ms']} ms)")]


def sensor_calibration(cfg) -> Dict[str, Any]:
    """Samples the configured source. In live modes the press MUST be idle (zero demand) during this."""
    src = make_source(cfg)

    async def go():
        await src.open()
        try:
            return await sample(src, 25, cfg["sample_period_s"])
        finally:
            await src.close()

    out: Dict[str, Any] = {"mode": cfg["mode"], "live": getattr(src, "live", False),
                           "offsets": {"flow_lpm": 0.0, "pressure_bar": 0.0}, "checks": []}
    if not src.live:
        out["checks"].append(check("sensors", "WARN",
                                   "SIMULATION mode: no real sensors are being read. Not valid for deployment."))
        return out
    try:
        samples, dur = asyncio.run(go())
    except (SensorError, OSError, Exception) as e:  # noqa: BLE001
        out["checks"].append(check("sensors:read", "FAIL", f"{type(e).__name__}: {e}"))
        return out
    q, p = np.array([s[0] for s in samples]), np.array([s[1] for s in samples])
    lim, zmax = cfg["sensor_limits"], cfg["max_zero_offset"]
    finite = np.isfinite(q).all() and np.isfinite(p).all()
    out["checks"].append(check("sensors:finite", "PASS" if finite else "FAIL", "all samples numeric" if finite else "NaN/inf in stream"))
    if not finite:
        return out
    stuck = np.ptp(q) == 0 and np.ptp(p) == 0
    out["checks"].append(check("sensors:alive", "FAIL" if stuck else "PASS",
                               "values never change (stuck/frozen sensor?)" if stuck else
                               f"{len(samples)} samples in {dur:.1f}s, noise sd flow={q.std():.2f} L/min, pressure={p.std():.2f} bar"))
    for name, arr, key in (("flow", q, "flow_lpm"), ("pressure", p, "pressure_bar")):
        off = float(np.median(arr))
        in_range = lim[key][0] - zmax[key] <= off <= lim[key][1]
        if abs(off) <= zmax[key]:
            out["offsets"][key] = off
            out["checks"].append(check(f"sensors:zero_{name}", "PASS",
                                       f"idle zero offset {off:+.2f} applied (limit +/-{zmax[key]})"))
        else:
            out["checks"].append(check(f"sensors:zero_{name}", "FAIL",
                                       f"idle reading {off:+.2f} exceeds +/-{zmax[key]}: press not idle or sensor/scaling wrong"
                                       + ("" if in_range else " (also outside configured range)")))
    return out


def preflight(cfg, run_sensor_cal: bool = True) -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    import sys
    checks.append(check("python", "PASS" if sys.version_info >= (3, 10) else "FAIL",
                        f"{sys.version.split()[0]} on {hardware.host_info()['os']}/{hardware.host_info()['machine']}"))
    missing = []
    for mod in ("numpy", "pandas", "sklearn", "asyncua", "matplotlib"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    checks.append(check("dependencies", "FAIL" if missing else "PASS",
                        f"missing: {', '.join(missing)}" if missing else "all required modules import"))
    if missing:
        return {"checks": checks, "ok": False, "sensor": None}
    try:
        state_dir()
        checks.append(check("state_dir", "PASS", state_dir()))
    except RuntimeError as e:
        checks.append(check("state_dir", "FAIL", str(e)))
    try:
        port = int(cfg["listen_endpoint"].rsplit(":", 1)[1].split("/")[0])
        with socket.socket() as s:
            s.bind(("0.0.0.0", port))
        checks.append(check("listen_port", "PASS", f"TCP {port} is free"))
    except OSError as e:
        checks.append(check("listen_port", "FAIL", f"cannot bind: {e}"))
    except (IndexError, ValueError):
        checks.append(check("listen_port", "FAIL", f"cannot parse {cfg['listen_endpoint']}"))
    checks += model_validation(cfg) + solver_check(cfg)
    if os.path.exists(TARIFF_META):
        meta = json.load(open(TARIFF_META))
        checks.append(check("tariff_data", "WARN" if meta.get("synthetic") else "PASS",
                            f"source={meta.get('source')} (synthetic={meta.get('synthetic')}); savings in EUR are illustrative"
                            if meta.get("synthetic") else f"source={meta.get('source')}"))
    sensor = sensor_calibration(cfg) if run_sensor_cal else None
    if sensor:
        checks += sensor["checks"]
    ok = not any(c["status"] == "FAIL" for c in checks)
    live_ready = ok and bool(sensor and sensor["live"])
    return {"checks": checks, "ok": ok, "live_ready": live_ready, "sensor": sensor,
            "pump_csv_sha256": file_sha256(PUMP_CSV), "host": hardware.host_info()}
