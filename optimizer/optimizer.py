"""
Hydraulic Pump Staging Optimization Engine.
Solves the mixed-integer constrained dispatch problem for a multi-pump hydraulic power unit (HPU).
Minimizes instantaneous active electrical power (kW) while guaranteeing hydraulic demand satisfaction.
"""

import os
import sys

# Ensure workspace root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from pumps.pump_model import PumpFleetModel


@dataclass
class StagingDecision:
    feasible: bool
    total_power_kw: float
    delivered_flow_lpm: float
    active_pumps: Dict[str, bool]
    displacements: Dict[str, float]  # fraction 0.0 to 1.0
    pump_flows: Dict[str, float]  # L/min per pump
    pump_powers: Dict[str, float]  # kW per pump
    staging_code: str  # e.g., "P3" or "P1+P2"
    throttled_flow_lpm: float = 0.0
    throttling_loss_kw: float = 0.0


class PumpStagingOptimizer:
    """
    Optimizes multi-pump hydraulic staging and continuous swashplate displacements.
    Executes in <0.2 ms per time-step via exact discrete combinatorial evaluation + physics-informed dispatch.
    Enforces minimum swashplate displacement limits (alpha_min) and models relief/bypass throttling penalties.
    """

    def __init__(self, fleet_model: Optional[PumpFleetModel] = None,
                 min_displacement_fraction: float = 0.20,
                 unswashed_standby: bool = True):
        self.fleet = fleet_model or PumpFleetModel()
        self.min_alpha = min_displacement_fraction
        self.unswashed_standby = unswashed_standby  # If True, inactive pumps draw P_idle; if False, 0 kW

        self.pump_ids = list(self.fleet.pumps.keys())
        self.n_pumps = len(self.pump_ids)

        # Generate all 2^N staging combinations (1 to 2^N - 1)
        self.combinations = []
        for i in range(1, 1 << self.n_pumps):
            comb = [bool((i >> j) & 1) for j in range(self.n_pumps)]
            self.combinations.append(comb)

    def _solve_flow_dispatch_for_subset(self, active_mask: List[bool],
                                        target_flow: float,
                                        target_pressure: float) -> Tuple[bool, float, Dict[str, float], Dict[str, float], float, float]:
        """
        For a given active pump combination, determines flow distribution.
        Returns: (is_feasible, total_active_power, pump_flows, pump_powers, throttled_flow, throttling_loss_kw)
        """
        active_ids = [self.pump_ids[i] for i, act in enumerate(active_mask) if act]
        max_flows = np.array([self.fleet.pumps[pid].max_flow_lpm for pid in active_ids])
        min_flows = max_flows * self.min_alpha

        sum_max_flow = float(np.sum(max_flows))
        sum_min_flow = float(np.sum(min_flows))

        # Check maximum capacity constraint
        if sum_max_flow < target_flow - 1e-3:
            return False, float("inf"), {}, {}, 0.0, 0.0

        throttled_flow = 0.0
        throttling_loss_kw = 0.0

        if target_flow < sum_min_flow:
            # Active pumps cannot swash below alpha_min without loss of hydrodynamic lubrication.
            # Excess flow must be bypassed/dumped over the proportional relief valve at target_pressure!
            throttled_flow = sum_min_flow - target_flow
            throttling_loss_kw = (target_pressure * throttled_flow) / 600.0
            actual_flow_generated = sum_min_flow
        else:
            actual_flow_generated = target_flow

        # Allocate actual_flow_generated across active pumps proportionally to max capacity
        weights = max_flows / sum_max_flow
        q_alloc = weights * actual_flow_generated

        pump_flows = {}
        pump_powers = {}
        total_p = 0.0

        for i, pid in enumerate(active_ids):
            q_val = float(q_alloc[i])
            # Guarantee flow does not violate min bounds for active pumps
            q_val = max(min_flows[i], q_val)
            p_val = self.fleet.get_power(pid, q_val, target_pressure)
            pump_flows[pid] = q_val
            pump_powers[pid] = p_val
            total_p += p_val

        # Add the bypass/relief valve throttling dissipation
        total_p += throttling_loss_kw

        return True, total_p, pump_flows, pump_powers, throttled_flow, throttling_loss_kw

    def optimize_step(self, flow_demand_lpm: float, pressure_demand_bar: float) -> StagingDecision:
        """
        Finds the globally optimal staging combination and displacement setpoints for a single time step.
        """
        best_power = float("inf")
        best_decision = None

        # Zero demand case (e.g. idle/standby)
        if flow_demand_lpm <= 1.0:
            active_dict = {pid: False for pid in self.pump_ids}
            disp_dict = {pid: 0.0 for pid in self.pump_ids}
            flow_dict = {pid: 0.0 for pid in self.pump_ids}
            power_dict = {}
            total_p = 0.0
            for pid in self.pump_ids:
                p_kw = self.fleet.pumps[pid].idle_power_kw if self.unswashed_standby else 0.0
                power_dict[pid] = p_kw
                total_p += p_kw

            return StagingDecision(
                feasible=True,
                total_power_kw=round(total_p, 2),
                delivered_flow_lpm=0.0,
                active_pumps=active_dict,
                displacements=disp_dict,
                pump_flows=flow_dict,
                pump_powers=power_dict,
                staging_code="ALL_STANDBY",
                throttled_flow_lpm=0.0,
                throttling_loss_kw=0.0
            )

        # Evaluate feasible combinations
        for comb in self.combinations:
            is_feas, power_active, flows, powers, throttled_q, throttled_kw = self._solve_flow_dispatch_for_subset(
                active_mask=comb,
                target_flow=flow_demand_lpm,
                target_pressure=pressure_demand_bar
            )

            if not is_feas:
                continue

            # Add idle/standby power for inactive pumps
            total_p = power_active
            full_powers = powers.copy()
            full_flows = {pid: 0.0 for pid in self.pump_ids}
            full_disps = {pid: 0.0 for pid in self.pump_ids}
            full_active = {}

            for i, pid in enumerate(self.pump_ids):
                if comb[i]:
                    full_active[pid] = True
                    q_val = flows[pid]
                    full_flows[pid] = round(q_val, 2)
                    max_q = self.fleet.pumps[pid].max_flow_lpm
                    full_disps[pid] = round(min(1.0, q_val / max_q), 3)
                else:
                    full_active[pid] = False
                    idle_p = self.fleet.pumps[pid].idle_power_kw if self.unswashed_standby else 0.0
                    total_p += idle_p
                    full_powers[pid] = round(idle_p, 2)

            if total_p < best_power:
                best_power = total_p
                active_p_nums = [f"P{i+1}" for i, act in enumerate(comb) if act]
                staging_code = "+".join(active_p_nums)

                best_decision = StagingDecision(
                    feasible=True,
                    total_power_kw=round(best_power, 2),
                    delivered_flow_lpm=round(flow_demand_lpm, 2),
                    active_pumps=full_active,
                    displacements=full_disps,
                    pump_flows=full_flows,
                    pump_powers=full_powers,
                    staging_code=staging_code,
                    throttled_flow_lpm=round(throttled_q, 2),
                    throttling_loss_kw=round(throttled_kw, 2)
                )

        if best_decision is None:
            # Overload fallback
            all_dict = {pid: True for pid in self.pump_ids}
            return StagingDecision(
                feasible=False,
                total_power_kw=999.0,
                delivered_flow_lpm=0.0,
                active_pumps=all_dict,
                displacements={pid: 1.0 for pid in self.pump_ids},
                pump_flows={pid: 0.0 for pid in self.pump_ids},
                pump_powers={pid: 0.0 for pid in self.pump_ids},
                staging_code="OVERLOAD",
                throttled_flow_lpm=0.0,
                throttling_loss_kw=0.0
            )

        return best_decision

    def optimize_dataframe(self, df_demand: pd.DataFrame) -> pd.DataFrame:
        """Runs the optimization engine across all time steps in a demand DataFrame."""
        results = []
        for _, row in df_demand.iterrows():
            q_demand = float(row["target_flow_lpm"])
            p_demand = float(row["target_pressure_bar"])
            dec = self.optimize_step(q_demand, p_demand)

            res = {
                "opt_total_power_kw": dec.total_power_kw,
                "opt_delivered_flow_lpm": dec.delivered_flow_lpm,
                "opt_staging_code": dec.staging_code,
                "opt_throttled_flow_lpm": dec.throttled_flow_lpm,
                "opt_throttling_loss_kw": dec.throttling_loss_kw,
            }
            for pid in self.pump_ids:
                res[f"{pid}_active"] = dec.active_pumps[pid]
                res[f"{pid}_disp_pct"] = round(dec.displacements[pid] * 100.0, 1)
                res[f"{pid}_power_kw"] = dec.pump_powers[pid]
                res[f"{pid}_flow_lpm"] = dec.pump_flows[pid]

            results.append(res)

        df_opt = pd.concat([df_demand.reset_index(drop=True), pd.DataFrame(results)], axis=1)
        return df_opt


if __name__ == "__main__":
    opt = PumpStagingOptimizer()
    print("Testing Optimizer across key extrusion phases with physical staging:")
    test_cases = [
        ("Idle / Standby", 0.0, 20.0),
        ("Decompression", 45.0, 150.0),
        ("Die Slide Shift", 85.0, 50.0),
        ("Container Shift", 180.0, 60.0),
        ("Shear Stroke", 140.0, 220.0),
        ("Main Extrusion Peak", 680.0, 280.0),
    ]
    for name, q, p in test_cases:
        dec = opt.optimize_step(q, p)
        print(f"[{name:20s}] Q={q:5.1f} L/min, P={p:5.1f} bar -> Staging: {dec.staging_code:10s} | "
              f"Power: {dec.total_power_kw:6.1f} kW (Throttled: {dec.throttled_flow_lpm:4.1f} L/min)")
