"""
Comparative Benchmarking Engine.
Compares Conventional Baseline Press Operation vs. HPEO Optimized Dynamic Staging.
Integrates ENTSO-E Spain Day-Ahead Spot Electricity Tariffs.
"""

import os
import sys

# Ensure workspace root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from simulator.press_demand import PressCycleSimulator
from optimizer.optimizer import PumpStagingOptimizer


class StagingBenchmark:
    """
    Evaluates hydraulic energy consumption, financial costs, and emissions
    under Baseline (All-Pumps Active) vs. HPEO (Optimized Dynamic Staging).
    """

    def __init__(self, optimizer: Optional[PumpStagingOptimizer] = None,
                 tariff_csv_path: Optional[str] = None):
        self.optimizer = optimizer or PumpStagingOptimizer()
        self.fleet = self.optimizer.fleet

        if tariff_csv_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            tariff_csv_path = os.path.join(base_dir, "data", "electricity_prices_es.csv")

        self.df_tariffs = pd.read_csv(tariff_csv_path)
        # Average spot price in EUR/kWh
        self.mean_tariff_eur_kwh = float(self.df_tariffs["price_eur_per_kwh"].mean())
        self.mean_tariff_eur_mwh = float(self.df_tariffs["price_eur_per_mwh"].mean())

    def compute_baseline_step(self, flow_demand_lpm: float, pressure_demand_bar: float) -> Dict[str, Any]:
        """
        Conventional baseline press HPU:
        - Common high-pressure header maintained at nominal rail pressure (min 220 bar).
        - Auxiliary movements throttle pressure down from rail pressure across proportional valves.
        - All 3 pumps remain continuously running (no staging).
        - Pumps cannot swash below min displacement (alpha_min); excess flow is dumped over main relief.
        """
        nominal_rail_pressure = max(220.0, pressure_demand_bar)

        if flow_demand_lpm <= 1.0:
            # Standby/idle: all 3 pumps running at circulation pressure (~40 bar)
            circulation_power = sum(
                self.fleet.get_power(pid, self.fleet.pumps[pid].max_flow_lpm * self.optimizer.min_alpha, 40.0)
                for pid in self.optimizer.pump_ids
            )
            return {
                "base_total_power_kw": round(circulation_power, 2),
                "base_throttling_loss_kw": 0.0,
                "base_staging_code": "ALL_CIRCULATION"
            }

        max_flows = np.array([p.max_flow_lpm for p in self.fleet.pumps.values()])
        min_flows = max_flows * self.optimizer.min_alpha
        sum_max = float(np.sum(max_flows))
        sum_min = float(np.sum(min_flows))

        # In conventional common-rail system, pumps deliver at rail pressure
        actual_gen = max(sum_min, flow_demand_lpm)
        throttled_flow = max(0.0, sum_min - flow_demand_lpm)
        # Throttling loss consists of:
        # 1. Excess flow dumped over relief valve at rail pressure
        # 2. Pressure drop from rail pressure (220 bar) down to auxiliary demand pressure (e.g. 60 bar)
        relief_dump_kw = (nominal_rail_pressure * throttled_flow) / 600.0
        valve_drop_kw = (max(0.0, nominal_rail_pressure - pressure_demand_bar) * flow_demand_lpm) / 600.0
        total_throttling_kw = relief_dump_kw + valve_drop_kw

        q_alloc = (max_flows / sum_max) * actual_gen
        total_p = 0.0
        for i, pid in enumerate(self.optimizer.pump_ids):
            q_i = max(min_flows[i], float(q_alloc[i]))
            total_p += self.fleet.get_power(pid, q_i, nominal_rail_pressure)

        return {
            "base_total_power_kw": round(total_p, 2),
            "base_throttling_loss_kw": round(total_throttling_kw, 2),
            "base_staging_code": "ALL_ACTIVE_RAIL"
        }

    def run_benchmark(self, df_demand: pd.DataFrame,
                      billet_mass_kg: float = 70.0,
                      annual_operating_hours: float = 5500.0) -> Dict[str, Any]:
        """
        Executes comparative simulation across demand timeseries.
        """
        # Run optimizer
        df_opt = self.optimizer.optimize_dataframe(df_demand)

        # Run baseline
        base_powers = []
        base_throttling = []
        for _, row in df_demand.iterrows():
            b_res = self.compute_baseline_step(row["target_flow_lpm"], row["target_pressure_bar"])
            base_powers.append(b_res["base_total_power_kw"])
            base_throttling.append(b_res["base_throttling_loss_kw"])

        df_opt["base_total_power_kw"] = base_powers
        df_opt["base_throttling_loss_kw"] = base_throttling
        df_opt["power_saved_kw"] = np.maximum(0.0, df_opt["base_total_power_kw"] - df_opt["opt_total_power_kw"])

        # Energy integration (kW * dt_hours = kWh)
        # Approximate dt from timestamps
        dt_s = float(np.diff(df_opt["timestamp"].values[:2])[0]) if len(df_opt) > 1 else 0.1
        dt_hours = dt_s / 3600.0

        base_total_kwh = float(np.sum(df_opt["base_total_power_kw"]) * dt_hours)
        opt_total_kwh = float(np.sum(df_opt["opt_total_power_kw"]) * dt_hours)
        saved_kwh = base_total_kwh - opt_total_kwh
        pct_savings = (saved_kwh / base_total_kwh) * 100.0 if base_total_kwh > 0 else 0.0

        # Aluminum production metrics
        num_cycles = int(df_demand["cycle_id"].nunique())
        total_tonnage = (num_cycles * billet_mass_kg) / 1000.0  # metric tons

        base_kwh_per_ton = base_total_kwh / total_tonnage if total_tonnage > 0 else 0.0
        opt_kwh_per_ton = opt_total_kwh / total_tonnage if total_tonnage > 0 else 0.0
        delta_kwh_per_ton = base_kwh_per_ton - opt_kwh_per_ton

        # Financial metrics using Spain spot tariff
        sim_duration_hours = (df_demand["timestamp"].iloc[-1] - df_demand["timestamp"].iloc[0]) / 3600.0
        avg_hourly_base_kw = base_total_kwh / sim_duration_hours
        avg_hourly_opt_kw = opt_total_kwh / sim_duration_hours
        avg_hourly_saved_kw = saved_kwh / sim_duration_hours

        # Annualized savings:
        annual_saved_kwh = avg_hourly_saved_kw * annual_operating_hours
        annual_financial_savings_eur = annual_saved_kwh * self.mean_tariff_eur_kwh

        # CO2 emissions reduction (Spain grid intensity ~0.140 kg CO2e / kWh)
        carbon_factor_kg_per_kwh = 0.140
        annual_co2_saved_tonnes = (annual_saved_kwh * carbon_factor_kg_per_kwh) / 1000.0

        summary = {
            "num_cycles": num_cycles,
            "sim_duration_seconds": round(df_demand["timestamp"].iloc[-1] - df_demand["timestamp"].iloc[0], 1),
            "total_aluminum_tonnes": round(total_tonnage, 3),
            "baseline_kwh": round(base_total_kwh, 3),
            "optimized_kwh": round(opt_total_kwh, 3),
            "saved_kwh": round(saved_kwh, 3),
            "energy_savings_pct": round(pct_savings, 2),
            "baseline_kwh_per_ton": round(base_kwh_per_ton, 2),
            "optimized_kwh_per_ton": round(opt_kwh_per_ton, 2),
            "delta_kwh_per_ton": round(delta_kwh_per_ton, 2),
            "mean_tariff_eur_mwh": round(self.mean_tariff_eur_mwh, 2),
            "mean_tariff_eur_kwh": round(self.mean_tariff_eur_kwh, 5),
            "annual_operating_hours": annual_operating_hours,
            "annual_saved_kwh": round(annual_saved_kwh, 1),
            "annual_financial_savings_eur": round(annual_financial_savings_eur, 2),
            "annual_co2_saved_tonnes": round(annual_co2_saved_tonnes, 2)
        }

        return {
            "summary": summary,
            "df_results": df_opt
        }


if __name__ == "__main__":
    from simulator.press_demand import PressCycleSimulator

    sim = PressCycleSimulator(seed=42)
    df_demand = sim.simulate_fleet_demand(num_cycles=5)

    benchmark = StagingBenchmark()
    res = benchmark.run_benchmark(df_demand)
    s = res["summary"]

    print("\n" + "=" * 65)
    print("      HPEO HYDRAULIC PUMP ENERGY OPTIMIZER - BENCHMARK REPORT")
    print("=" * 65)
    print(f"Cycles Evaluated:            {s['num_cycles']} press cycles ({s['total_aluminum_tonnes']} tonnes)")
    print(f"Baseline Energy:             {s['baseline_kwh']:.2f} kWh  ({s['baseline_kwh_per_ton']:.1f} kWh/ton)")
    print(f"HPEO Optimized Energy:       {s['optimized_kwh']:.2f} kWh  ({s['optimized_kwh_per_ton']:.1f} kWh/ton)")
    print(f"Specific Energy Saved:       {s['delta_kwh_per_ton']:.1f} kWh/ton ({s['energy_savings_pct']:.1f}% reduction)")
    print("-" * 65)
    print(f"Spain ENTSO-E Mean Tariff:   {s['mean_tariff_eur_mwh']:.2f} EUR/MWh")
    print(f"Annual Operating Hours:      {s['annual_operating_hours']:.0f} hrs/year (3-shift duty)")
    print(f"Annual Energy Saved:         {s['annual_saved_kwh']:,.0f} kWh/year")
    print(f"Annual Financial Savings:    EUR {s['annual_financial_savings_eur']:,.2f} / year")
    print(f"CO2 Emissions Avoided:       {s['annual_co2_saved_tonnes']:.1f} metric tonnes CO2e / year")
    print("=" * 65 + "\n")
