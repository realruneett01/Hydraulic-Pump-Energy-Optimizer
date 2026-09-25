"""
Unit tests for PumpFleetModel and SinglePumpModel.
Validates physical monotonicity, bounds, and fitting accuracy (MAPE < 5%).
"""

import pytest
import numpy as np
from pumps.pump_model import PumpFleetModel


@pytest.fixture(scope="module")
def fleet():
    return PumpFleetModel()


def test_fleet_loading(fleet):
    specs = fleet.get_pump_specs()
    assert len(specs) == 3
    pump_ids = [s["pump_id"] for s in specs]
    assert "pump_1" in pump_ids
    assert "pump_2" in pump_ids
    assert "pump_3" in pump_ids


def test_standby_idle_power(fleet):
    for pid in ["pump_1", "pump_2", "pump_3"]:
        power_standby = fleet.get_power(pid, flow_lpm=0.0, pressure_bar=20.0)
        assert power_standby > 0.0
        # Standby should be under 15 kW even for the largest pump
        assert power_standby < 15.0


def test_monotonicity_flow(fleet):
    """At fixed pressure, increasing flow must strictly increase shaft power."""
    pressures = [50.0, 150.0, 250.0, 300.0]
    for pid, pump in fleet.pumps.items():
        max_q = pump.max_flow_lpm
        flows = np.linspace(20.0, max_q, 15)
        for p in pressures:
            powers = [fleet.get_power(pid, q, p) for q in flows]
            # Check strictly non-decreasing
            diffs = np.diff(powers)
            assert np.all(diffs >= -1e-4), f"Power not monotonic with flow for {pid} at {p} bar: {diffs}"


def test_monotonicity_pressure(fleet):
    """At fixed flow, increasing pressure must strictly increase shaft power."""
    pressures = np.linspace(30.0, 300.0, 15)
    for pid, pump in fleet.pumps.items():
        test_flows = [pump.max_flow_lpm * 0.3, pump.max_flow_lpm * 0.7, pump.max_flow_lpm]
        for q in test_flows:
            powers = [fleet.get_power(pid, q, p) for p in pressures]
            diffs = np.diff(powers)
            assert np.all(diffs >= -1e-4), f"Power not monotonic with pressure for {pid} at flow {q}: {diffs}"


def test_mape_accuracy(fleet):
    """Mean Absolute Percentage Error against raw datasheet points must be under 5%."""
    for pid, pump in fleet.pumps.items():
        raw = pump.raw_data[pump.raw_data["flow_lpm"] > 0]
        actual = raw["shaft_power_kw"].values
        predicted = np.array([
            fleet.get_power(pid, q, p)
            for q, p in zip(raw["flow_lpm"], raw["pressure_bar"])
        ])
        mape = np.mean(np.abs((actual - predicted) / actual)) * 100.0
        assert mape < 5.0, f"MAPE too high for {pid}: {mape:.2f}% (must be < 5%)"


def test_efficiency_bounds(fleet):
    """Pump efficiency must remain between 0.0 and 0.95."""
    for pid, pump in fleet.pumps.items():
        raw = pump.raw_data[pump.raw_data["flow_lpm"] > 0]
        for q, p in zip(raw["flow_lpm"], raw["pressure_bar"]):
            eta = fleet.get_efficiency(pid, q, p)
            assert 0.0 <= eta <= 0.95, f"Invalid efficiency {eta} for {pid} at Q={q}, P={p}"
