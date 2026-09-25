"""
Unit tests for PumpStagingOptimizer and StagingBenchmark.
Validates constraint satisfaction, power minimization, and physical bounding.
"""

import pytest
import numpy as np
from simulator.press_demand import PressCycleSimulator
from optimizer.optimizer import PumpStagingOptimizer
from optimizer.benchmark import StagingBenchmark


@pytest.fixture(scope="module")
def optimizer():
    return PumpStagingOptimizer()


@pytest.fixture(scope="module")
def benchmark(optimizer):
    return StagingBenchmark(optimizer=optimizer)


@pytest.fixture(scope="module")
def demand_df():
    sim = PressCycleSimulator(dt_seconds=0.2, seed=99)
    return sim.simulate_fleet_demand(num_cycles=2)


def test_zero_demand_standby(optimizer):
    dec = optimizer.optimize_step(flow_demand_lpm=0.0, pressure_demand_bar=20.0)
    assert dec.feasible is True
    assert dec.staging_code == "ALL_STANDBY"
    assert all(not act for act in dec.active_pumps.values())
    assert all(d == 0.0 for d in dec.displacements.values())
    assert dec.total_power_kw > 0.0  # Draws idle standby power


def test_delivered_flow_satisfies_demand(optimizer):
    test_demands = [30.0, 85.0, 140.0, 220.0, 360.0, 550.0, 720.0]
    for q in test_demands:
        dec = optimizer.optimize_step(flow_demand_lpm=q, pressure_demand_bar=250.0)
        assert dec.feasible is True
        assert dec.delivered_flow_lpm >= q - 1e-2, f"Failed flow satisfaction for demand {q}"


def test_displacements_within_bounds(optimizer, demand_df):
    df_opt = optimizer.optimize_dataframe(demand_df)
    for pid in optimizer.pump_ids:
        disps = df_opt[f"{pid}_disp_pct"].values
        assert np.all(disps >= 0.0) and np.all(disps <= 100.0)


def test_optimized_power_le_baseline(benchmark, demand_df):
    res = benchmark.run_benchmark(demand_df)
    df_res = res["df_results"]
    power_diff = df_res["base_total_power_kw"] - df_res["opt_total_power_kw"]
    # Allow tiny float precision epsilon
    assert np.all(power_diff >= -0.05), "Optimized power must be <= baseline power at every timestep"


def test_benchmark_positive_energy_savings(benchmark, demand_df):
    res = benchmark.run_benchmark(demand_df)
    s = res["summary"]
    assert s["saved_kwh"] > 0.0
    assert s["energy_savings_pct"] > 0.0
    assert s["annual_financial_savings_eur"] > 0.0
