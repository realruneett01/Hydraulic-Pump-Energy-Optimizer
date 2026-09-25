"""
Hydraulic Pump Fleet Modeling and Efficiency Surrogate Regressors.
Fits 2D polynomial surfaces from manufacturer datasheet points (Bosch Rexroth, Parker)
mapping (Flow [L/min], Pressure [bar]) -> Shaft Input Power [kW].
"""

import os
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import Ridge
import matplotlib.pyplot as plt


class SinglePumpModel:
    """Surrogate power model for an individual axial piston pump."""

    def __init__(self, pump_id: str, manufacturer: str, model_name: str,
                 displacement_cc: float, rated_rpm: float, idle_power_kw: float,
                 df_pump_data: pd.DataFrame):
        self.pump_id = pump_id
        self.manufacturer = manufacturer
        self.model_name = model_name
        self.displacement_cc = displacement_cc
        self.rated_rpm = rated_rpm
        self.idle_power_kw = idle_power_kw
        self.raw_data = df_pump_data.copy()

        # Compute max theoretical and rated flow
        self.max_flow_lpm = float(df_pump_data["flow_lpm"].max())
        self.max_pressure_bar = float(df_pump_data["pressure_bar"].max())
        self.max_power_kw = float(df_pump_data["shaft_power_kw"].max())

        # Fit polynomial regression (degree 2 with Ridge regularization)
        self.poly = PolynomialFeatures(degree=2, include_bias=True)
        self.regressor = Ridge(alpha=1e-3)

        X = self.raw_data[["flow_lpm", "pressure_bar"]].values
        y = self.raw_data["shaft_power_kw"].values
        X_poly = self.poly.fit_transform(X)
        self.regressor.fit(X_poly, y)

    def predict_power(self, flow_lpm: float, pressure_bar: float) -> float:
        """
        Predict required shaft power in kW for a given flow and pressure.
        Enforces physical bounds:
        - If flow <= 0.05 and pressure <= 30 bar, returns idle standby power.
        - Output is never lower than idle standby power.
        """
        if flow_lpm <= 0.05:
            # Standby/unswashed condition
            return float(self.idle_power_kw * max(1.0, pressure_bar / 20.0 * 0.2))

        # Clamp inputs to safe physical limits
        q_clamped = max(0.0, min(flow_lpm, self.max_flow_lpm * 1.05))
        p_clamped = max(10.0, min(pressure_bar, self.max_pressure_bar * 1.05))

        X_input = np.array([[q_clamped, p_clamped]])
        X_poly = self.poly.transform(X_input)
        power_pred = float(self.regressor.predict(X_poly)[0])

        # Enforce physics: power must exceed pure theoretical hydraulic power
        # P_hyd = (P [bar] * Q [L/min]) / 600
        p_hyd = (p_clamped * q_clamped) / 600.0
        # Axial piston pumps have an efficiency <= ~95%, so shaft power >= p_hyd / 0.96
        min_physical_power = max(self.idle_power_kw, p_hyd / 0.96)

        return float(max(min_physical_power, power_pred))

    def predict_efficiency(self, flow_lpm: float, pressure_bar: float) -> float:
        """
        Compute overall total efficiency (eta_total = P_hydraulic / P_shaft).
        Returns a float between 0.0 and 1.0.
        """
        if flow_lpm <= 0.1 or pressure_bar <= 5.0:
            return 0.0
        p_hyd = (pressure_bar * flow_lpm) / 600.0
        p_shaft = self.predict_power(flow_lpm, pressure_bar)
        if p_shaft <= 0.0:
            return 0.0
        return float(min(0.95, max(0.0, p_hyd / p_shaft)))


class PumpFleetModel:
    """Manages the full pump fleet installed on the hydraulic power unit."""

    def __init__(self, csv_path: str = None):
        if csv_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            csv_path = os.path.join(base_dir, "data", "raw_pump_curves.csv")

        self.csv_path = csv_path
        self.df = pd.read_csv(csv_path)
        self.pumps: Dict[str, SinglePumpModel] = {}
        self._load_and_fit_all()

    def _load_and_fit_all(self):
        pump_ids = self.df["pump_id"].unique()
        for pid in pump_ids:
            sub_df = self.df[self.df["pump_id"] == pid].copy()
            manufacturer = sub_df["manufacturer"].iloc[0]
            model_name = sub_df["model"].iloc[0]
            displacement = float(sub_df["displacement_cc"].iloc[0])
            rpm = float(sub_df["rated_rpm"].iloc[0])

            # Idle power is the power when flow == 0
            idle_rows = sub_df[sub_df["flow_lpm"] == 0]
            idle_kw = float(idle_rows["shaft_power_kw"].iloc[0]) if len(idle_rows) > 0 else 5.0

            self.pumps[pid] = SinglePumpModel(
                pump_id=pid,
                manufacturer=manufacturer,
                model_name=model_name,
                displacement_cc=displacement,
                rated_rpm=rpm,
                idle_power_kw=idle_kw,
                df_pump_data=sub_df
            )

    def get_power(self, pump_id: str, flow_lpm: float, pressure_bar: float) -> float:
        if pump_id not in self.pumps:
            raise KeyError(f"Pump '{pump_id}' not found in fleet.")
        return self.pumps[pump_id].predict_power(flow_lpm, pressure_bar)

    def get_efficiency(self, pump_id: str, flow_lpm: float, pressure_bar: float) -> float:
        if pump_id not in self.pumps:
            raise KeyError(f"Pump '{pump_id}' not found in fleet.")
        return self.pumps[pump_id].predict_efficiency(flow_lpm, pressure_bar)

    def get_pump_specs(self) -> List[Dict[str, Any]]:
        specs = []
        for pid, p in self.pumps.items():
            specs.append({
                "pump_id": pid,
                "manufacturer": p.manufacturer,
                "model": p.model_name,
                "displacement_cc": p.displacement_cc,
                "rated_rpm": p.rated_rpm,
                "max_flow_lpm": p.max_flow_lpm,
                "max_pressure_bar": p.max_pressure_bar,
                "max_power_kw": p.max_power_kw,
                "idle_power_kw": p.idle_power_kw
            })
        return specs

    def generate_fit_verification_plot(self, output_path: str = None) -> str:
        """Generates side-by-side verification plots comparing regression surfaces vs. datasheet points."""
        if output_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            output_path = os.path.join(base_dir, "curve_fit_check.png")

        fig, axes = plt.subplots(1, len(self.pumps), figsize=(6 * len(self.pumps), 5), sharey=False)
        if len(self.pumps) == 1:
            axes = [axes]

        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

        for idx, (pid, pump) in enumerate(self.pumps.items()):
            ax = axes[idx]
            raw = pump.raw_data[pump.raw_data["flow_lpm"] > 0]
            pressures = sorted(raw["pressure_bar"].unique())

            for p_idx, p_bar in enumerate(pressures):
                subset = raw[raw["pressure_bar"] == p_bar].sort_values("flow_lpm")
                if len(subset) == 0:
                    continue
                color = colors[p_idx % len(colors)]
                # Plot raw points
                ax.scatter(subset["flow_lpm"], subset["shaft_power_kw"],
                           color=color, edgecolors="black", s=50,
                           label=f"{int(p_bar)} bar (Raw)" if idx == 0 else "")

                # Plot continuous regression curve
                q_smooth = np.linspace(subset["flow_lpm"].min(), subset["flow_lpm"].max(), 50)
                p_smooth = [pump.predict_power(q, p_bar) for q in q_smooth]
                ax.plot(q_smooth, p_smooth, linestyle="--", color=color, alpha=0.85,
                        label=f"{int(p_bar)} bar (Fitted)" if idx == 0 else "")

            ax.set_title(f"{pump.manufacturer} {pump.model_name}\n({pump.displacement_cc:.0f} cc/rev)",
                         fontsize=12, fontweight="bold")
            ax.set_xlabel("Flow (L/min)", fontsize=10)
            ax.set_ylabel("Shaft Power (kW)", fontsize=10)
            ax.grid(True, linestyle=":", alpha=0.6)

        fig.suptitle("HPEO Pump Power Curve Regressions vs. Manufacturer Datasheets",
                     fontsize=14, fontweight="bold", y=1.02)
        if len(self.pumps) > 0:
            axes[0].legend(loc="upper left", fontsize=8, framealpha=0.8)

        plt.tight_layout()
        plt.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"Fit verification plot saved -> {output_path}")
        return output_path


if __name__ == "__main__":
    fleet = PumpFleetModel()
    print("Loaded pump fleet:")
    for spec in fleet.get_pump_specs():
        print(f" - {spec['pump_id']}: {spec['manufacturer']} {spec['model']} ({spec['displacement_cc']} cc, "
              f"Max Flow={spec['max_flow_lpm']:.1f} L/min, Idle={spec['idle_power_kw']:.1f} kW)")
    fleet.generate_fit_verification_plot()
