"""
Unit tests for the PressCycleSimulator.
Validates phase continuity, ordering, physical constraints, and timestamp monotonicity.
"""

import pytest
import numpy as np
from simulator.press_demand import PressCycleSimulator


@pytest.fixture
def simulator():
    return PressCycleSimulator(dt_seconds=0.1, seed=123)


def test_single_cycle_phases(simulator):
    df_cycle, next_time = simulator.simulate_cycle(cycle_id=1, start_time=0.0)

    # Verify all sequential phases are present
    expected_phases = [
        "decompression",
        "container_shift_open",
        "shear_stroke",
        "die_slide_shift",
        "billet_load_and_seal",
        "main_extrusion_stroke",
        "inter_billet_dwell"
    ]

    unique_phases_in_order = []
    for p in df_cycle["phase_name"]:
        if not unique_phases_in_order or unique_phases_in_order[-1] != p:
            unique_phases_in_order.append(p)

    assert unique_phases_in_order == expected_phases, "Phases do not occur in expected physical sequence"


def test_timestamp_monotonicity(simulator):
    df_demand = simulator.simulate_fleet_demand(num_cycles=3)
    timestamps = df_demand["timestamp"].values
    diffs = np.diff(timestamps)
    assert np.all(diffs > 0), "Timestamps must be strictly monotonically increasing"


def test_demand_bounds(simulator):
    df_demand = simulator.simulate_fleet_demand(num_cycles=3)

    # Pressure must be between 15 and 320 bar
    assert df_demand["target_pressure_bar"].min() >= 15.0
    assert df_demand["target_pressure_bar"].max() <= 320.0

    # Flow must be between 0 and 750 L/min
    assert df_demand["target_flow_lpm"].min() >= 0.0
    assert df_demand["target_flow_lpm"].max() <= 750.0


def test_cycle_duration_bounds(simulator):
    df_cycle, next_time = simulator.simulate_cycle(cycle_id=1, start_time=0.0)
    duration = df_cycle["timestamp"].iloc[-1] - df_cycle["timestamp"].iloc[0]
    # Standard extrusion cycle should be between 40s and 80s
    assert 40.0 <= duration <= 80.0, f"Cycle duration {duration:.1f}s outside realistic range"


def test_extrusion_phase_dominates_energy(simulator):
    df_cycle, _ = simulator.simulate_cycle(cycle_id=1, start_time=0.0)
    # Hydraulic energy proxy = sum(P * Q * dt)
    df_cycle["energy_proxy"] = df_cycle["target_flow_lpm"] * df_cycle["target_pressure_bar"]

    extrusion_energy = df_cycle[df_cycle["phase_name"] == "main_extrusion_stroke"]["energy_proxy"].sum()
    total_energy = df_cycle["energy_proxy"].sum()

    extrusion_ratio = extrusion_energy / total_energy
    assert extrusion_ratio >= 0.70, f"Main extrusion should represent >70% of cycle energy, got {extrusion_ratio:.2%}"
