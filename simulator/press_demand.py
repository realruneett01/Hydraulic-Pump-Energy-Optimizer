"""
Extrusion Press Cycle & Hydraulic Demand Simulator.
Simulates a modern industrial aluminum extrusion press across 6 operational phases:
1. Decompression
2. Container Shift (Open)
3. Discard Shear Stroke
4. Die Slide Shift
5. Billet Load & Container Seal
6. Main Extrusion Stroke (Ram Forward)

Generates time-series hydraulic demand: Flow (L/min) and Pressure (bar).
"""

import os
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


@dataclass
class PhaseSpec:
    name: str
    nominal_duration_s: float
    duration_std_s: float
    base_flow_lpm: float
    flow_profile_type: str  # 'constant', 'ramp_down', 'ramp_up', 'extrusion_curve'
    base_pressure_bar: float
    pressure_profile_type: str  # 'constant', 'ramp_down', 'ramp_up', 'extrusion_curve'


class PressCycleSimulator:
    """
    Simulates high-fidelity extrusion press hydraulic duty cycles.
    """

    DEFAULT_PHASES = [
        PhaseSpec("decompression", nominal_duration_s=1.5, duration_std_s=0.1,
                  base_flow_lpm=45.0, flow_profile_type="constant",
                  base_pressure_bar=280.0, pressure_profile_type="ramp_down"),
        PhaseSpec("container_shift_open", nominal_duration_s=3.2, duration_std_s=0.2,
                  base_flow_lpm=175.0, flow_profile_type="constant",
                  base_pressure_bar=60.0, pressure_profile_type="constant"),
        PhaseSpec("shear_stroke", nominal_duration_s=2.2, duration_std_s=0.15,
                  base_flow_lpm=135.0, flow_profile_type="constant",
                  base_pressure_bar=210.0, pressure_profile_type="constant"),
        PhaseSpec("die_slide_shift", nominal_duration_s=1.8, duration_std_s=0.15,
                  base_flow_lpm=80.0, flow_profile_type="constant",
                  base_pressure_bar=50.0, pressure_profile_type="constant"),
        PhaseSpec("billet_load_and_seal", nominal_duration_s=3.8, duration_std_s=0.25,
                  base_flow_lpm=160.0, flow_profile_type="constant",
                  base_pressure_bar=120.0, pressure_profile_type="ramp_up"),
        PhaseSpec("main_extrusion_stroke", nominal_duration_s=38.0, duration_std_s=2.0,
                  base_flow_lpm=520.0, flow_profile_type="extrusion_curve",
                  base_pressure_bar=265.0, pressure_profile_type="extrusion_curve"),
        PhaseSpec("inter_billet_dwell", nominal_duration_s=7.5, duration_std_s=0.5,
                  base_flow_lpm=0.0, flow_profile_type="constant",
                  base_pressure_bar=20.0, pressure_profile_type="constant"),
    ]

    def __init__(self, dt_seconds: float = 0.1, seed: Optional[int] = 42,
                 custom_phases: Optional[List[PhaseSpec]] = None):
        self.dt = dt_seconds
        self.rng = np.random.default_rng(seed)
        self.phases = custom_phases or self.DEFAULT_PHASES

    def simulate_single_phase(self, spec: PhaseSpec, start_time: float, cycle_id: int,
                              start_ram_mm: float) -> Tuple[pd.DataFrame, float, float]:
        # Duration with Gaussian jitter (clamped to realistic minimum)
        dur = max(0.4, float(self.rng.normal(spec.nominal_duration_s, spec.duration_std_s)))
        n_steps = max(2, int(np.round(dur / self.dt)))
        t_arr = np.linspace(start_time, start_time + dur, n_steps)
        progress = np.linspace(0.0, 1.0, n_steps)

        # Flow calculation based on phase profile
        if spec.base_flow_lpm == 0.0:
            flow = np.zeros(n_steps)
        elif spec.flow_profile_type == "constant":
            flow = np.full(n_steps, spec.base_flow_lpm) + self.rng.normal(0, 2.5, n_steps)
        elif spec.flow_profile_type == "ramp_down":
            flow = spec.base_flow_lpm * (1.0 - 0.7 * progress) + self.rng.normal(0, 1.5, n_steps)
        elif spec.flow_profile_type == "ramp_up":
            flow = spec.base_flow_lpm * (0.3 + 0.7 * progress) + self.rng.normal(0, 2.0, n_steps)
        elif spec.flow_profile_type == "extrusion_curve":
            # Isothermal extrusion profile:
            # - Initial acceleration and breakout upset (0-15% of stroke): peak flow ~620 L/min
            # - Isothermal thermal compensation: ram speed decreases as billet heats up,
            #   tapering flow down from ~520 L/min to ~330 L/min (allowing pump staging!)
            accel_mask = progress < 0.10
            steady_mask = (progress >= 0.10) & (progress < 0.85)
            taper_mask = progress >= 0.85

            flow = np.zeros(n_steps)
            flow[accel_mask] = (spec.base_flow_lpm * 1.15) * (0.4 + 0.6 * progress[accel_mask] / 0.10)
            # Smooth thermal taper during steady extrusion
            taper_progress = (progress[steady_mask] - 0.10) / 0.75
            flow[steady_mask] = (spec.base_flow_lpm * 1.15) - ((spec.base_flow_lpm * 1.15) - 340.0) * taper_progress
            # Final deceleration before discard cut
            flow[taper_mask] = 340.0 * (1.0 - 0.4 * ((progress[taper_mask] - 0.85) / 0.15))
            flow += self.rng.normal(0, 4.0, n_steps)
        else:
            flow = np.full(n_steps, spec.base_flow_lpm)

        flow = np.clip(flow, 0.0 if spec.base_flow_lpm == 0.0 else 5.0, 750.0)

        # Pressure calculation based on phase profile
        if spec.pressure_profile_type == "constant":
            pressure = np.full(n_steps, spec.base_pressure_bar) + self.rng.normal(0, 2.0, n_steps)
        elif spec.pressure_profile_type == "ramp_down":
            # Decompression: drops from high pressure down to tank/idle level ~20 bar
            pressure = spec.base_pressure_bar * (1.0 - progress) + 20.0 * progress + self.rng.normal(0, 1.5, n_steps)
        elif spec.pressure_profile_type == "ramp_up":
            # Sealing: climbs from idle to seal pressure
            pressure = 25.0 + (spec.base_pressure_bar - 25.0) * progress + self.rng.normal(0, 2.0, n_steps)
        elif spec.pressure_profile_type == "extrusion_curve":
            # Breakout pressure spike, then steady pressure drop as billet length in container shortens
            # (friction decreases with decreasing billet length)
            breakout_mask = progress < 0.12
            breakout_peak = spec.base_pressure_bar * 1.12

            pressure = np.zeros(n_steps)
            # Breakout ramp
            pressure[breakout_mask] = spec.base_pressure_bar * 0.7 + (breakout_peak - spec.base_pressure_bar * 0.7) * (progress[breakout_mask] / 0.12)
            # Friction decay: from breakout back down to ~75% nominal at end
            decay_progress = (progress[~breakout_mask] - 0.12) / 0.88
            pressure[~breakout_mask] = breakout_peak - (breakout_peak - spec.base_pressure_bar * 0.78) * decay_progress
            pressure += self.rng.normal(0, 3.5, n_steps)
        else:
            pressure = np.full(n_steps, spec.base_pressure_bar)

        pressure = np.clip(pressure, 15.0, 320.0)

        # Ram position calculation
        ram_pos = np.full(n_steps, start_ram_mm)
        if spec.name == "main_extrusion_stroke":
            # Extrusion ram advances ~800 mm
            ram_pos = start_ram_mm + progress * 800.0
            end_ram = start_ram_mm + 800.0
        elif spec.name == "container_shift_open":
            # Ram retracts back to 0 mm for next billet
            end_ram = 0.0
            ram_pos = np.maximum(0.0, start_ram_mm - progress * start_ram_mm)
        else:
            end_ram = start_ram_mm

        df_phase = pd.DataFrame({
            "timestamp": np.round(t_arr, 2),
            "cycle_id": cycle_id,
            "phase_name": spec.name,
            "target_flow_lpm": np.round(flow, 2),
            "target_pressure_bar": np.round(pressure, 2),
            "ram_position_mm": np.round(ram_pos, 1)
        })

        next_time = float(t_arr[-1] + self.dt)
        return df_phase, next_time, end_ram

    def simulate_cycle(self, cycle_id: int = 1, start_time: float = 0.0) -> Tuple[pd.DataFrame, float]:
        """Simulates all 6 sequential phases for one complete billet cycle."""
        frames = []
        cur_time = start_time
        ram_mm = 0.0

        for phase_spec in self.phases:
            df_phase, cur_time, ram_mm = self.simulate_single_phase(
                spec=phase_spec, start_time=cur_time, cycle_id=cycle_id, start_ram_mm=ram_mm
            )
            frames.append(df_phase)

        df_cycle = pd.concat(frames, ignore_index=True)
        return df_cycle, cur_time

    def simulate_fleet_demand(self, num_cycles: int = 5) -> pd.DataFrame:
        """Simulates multiple consecutive extrusion press cycles."""
        all_cycles = []
        cur_time = 0.0
        for c in range(1, num_cycles + 1):
            df_c, cur_time = self.simulate_cycle(cycle_id=c, start_time=cur_time)
            all_cycles.append(df_c)
        return pd.concat(all_cycles, ignore_index=True)


def plot_demand_profile(df: pd.DataFrame, output_path: str = None) -> str:
    """Plots multi-phase hydraulic demand (flow and pressure) with phase color zones."""
    if output_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base_dir, "press_demand_profile.png")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    phase_colors = {
        "decompression": "#ff9999",
        "container_shift_open": "#66b3ff",
        "shear_stroke": "#99ff99",
        "die_slide_shift": "#ffcc99",
        "billet_load_and_seal": "#c2c2f0",
        "main_extrusion_stroke": "#ffb3e6"
    }

    # Plot Flow on Top
    ax1.plot(df["timestamp"], df["target_flow_lpm"], color="#0055aa", linewidth=1.5, label="Demand Flow (L/min)")
    ax1.set_ylabel("Flow Demand (L/min)", fontsize=11, fontweight="bold")
    ax1.set_title("HPEO Extrusion Press Hydraulic Demand Profile", fontsize=14, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left")

    # Plot Pressure on Bottom
    ax2.plot(df["timestamp"], df["target_pressure_bar"], color="#cc2200", linewidth=1.5, label="Demand Pressure (bar)")
    ax2.set_xlabel("Time (seconds)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Pressure Demand (bar)", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="upper left")

    # Overlay phase background regions
    phases_unique = df["phase_name"].unique()
    cycle_1 = df[df["cycle_id"] == 1]
    for p_name in phases_unique:
        p_df = cycle_1[cycle_1["phase_name"] == p_name]
        if len(p_df) > 0:
            t_start = p_df["timestamp"].iloc[0]
            t_end = p_df["timestamp"].iloc[-1]
            color = phase_colors.get(p_name, "#cccccc")
            ax1.axvspan(t_start, t_end, color=color, alpha=0.25, label=f"Phase: {p_name}")
            ax2.axvspan(t_start, t_end, color=color, alpha=0.25)

    # Clean legend for phase colors
    handles, labels = ax1.get_legend_handles_labels()
    # Keep unique labels
    by_label = dict(zip(labels, handles))
    ax1.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=8, framealpha=0.9)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Demand profile visualization saved -> {output_path}")
    return output_path


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_csv = os.path.join(base_dir, "data", "sample_demand_profile.csv")

    sim = PressCycleSimulator(dt_seconds=0.1, seed=42)
    df_demand = sim.simulate_fleet_demand(num_cycles=5)
    df_demand.to_csv(output_csv, index=False)
    print(f"Generated {len(df_demand)} demand samples across 5 cycles -> {output_csv}")

    plot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "press_demand_profile.png")
    plot_demand_profile(df_demand[df_demand["cycle_id"] <= 2], output_path=plot_path)
