"""
Industrial OPC-UA Server for HPEO Press Telemetry & Pump Staging Setpoints.
Exposes real-time press and HPU variables over standard OPC-UA (IEC 62541).
Simulates direct integration with machine PLC / SCADA.
"""

import os
import sys
import asyncio
import logging

# Ensure workspace root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from asyncua import Server, ua
import pandas as pd
from simulator.press_demand import PressCycleSimulator
from optimizer.optimizer import PumpStagingOptimizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OPCUA_Server")


async def run_opcua_server(endpoint: str = "opc.tcp://127.0.0.1:4840/freeopcua/server/",
                           playback_speed: float = 1.0,
                           max_cycles: int = 5):
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("HPEO Hydraulic Press Optimization Server")

    # Setup namespace
    uri = "http://industrial.automation/hpeo/"
    ns_idx = await server.register_namespace(uri)

    # Get Objects folder
    objects = server.nodes.objects

    # Create HPEO Folder
    hpeo_folder = await objects.add_folder(ns_idx, "HPEO_Press_HPU")

    # 1. Press Telemetry Nodes
    press_folder = await hpeo_folder.add_folder(ns_idx, "PressTelemetry")
    tag_phase = await press_folder.add_variable(ns_idx, "PressPhase", "idle", ua.VariantType.String)
    tag_flow_demand = await press_folder.add_variable(ns_idx, "DemandFlow_LPM", 0.0, ua.VariantType.Float)
    tag_press_demand = await press_folder.add_variable(ns_idx, "DemandPressure_Bar", 20.0, ua.VariantType.Float)
    tag_cycle_time = await press_folder.add_variable(ns_idx, "CycleTime_s", 0.0, ua.VariantType.Float)
    tag_cycle_id = await press_folder.add_variable(ns_idx, "CycleId", 1, ua.VariantType.Int32)

    # 2. Pump Staging & Setpoint Nodes
    pump_folder = await hpeo_folder.add_folder(ns_idx, "PumpSetpoints")
    tag_staging_code = await pump_folder.add_variable(ns_idx, "StagingCode", "ALL_STANDBY", ua.VariantType.String)

    # Individual Pump Tags
    pump_tags = {}
    for p_num in [1, 2, 3]:
        p_sub = await pump_folder.add_folder(ns_idx, f"Pump{p_num}")
        pump_tags[f"pump_{p_num}"] = {
            "active": await p_sub.add_variable(ns_idx, f"Pump{p_num}_Active", False, ua.VariantType.Boolean),
            "disp_pct": await p_sub.add_variable(ns_idx, f"Pump{p_num}_DisplacementPct", 0.0, ua.VariantType.Float),
            "power_kw": await p_sub.add_variable(ns_idx, f"Pump{p_num}_PowerKW", 0.0, ua.VariantType.Float),
            "flow_lpm": await p_sub.add_variable(ns_idx, f"Pump{p_num}_FlowLPM", 0.0, ua.VariantType.Float),
        }

    # 3. Grid & Cost Analytics Nodes
    grid_folder = await hpeo_folder.add_folder(ns_idx, "EnergyAndTariffs")
    tag_tariff = await grid_folder.add_variable(ns_idx, "GridTariff_EUR_MWh", 64.28, ua.VariantType.Float)
    tag_opt_power = await grid_folder.add_variable(ns_idx, "InstantaneousPower_KW", 0.0, ua.VariantType.Float)
    tag_base_power = await grid_folder.add_variable(ns_idx, "BaselinePower_KW", 0.0, ua.VariantType.Float)
    tag_instant_savings = await grid_folder.add_variable(ns_idx, "InstantaneousSavings_EUR_hr", 0.0, ua.VariantType.Float)

    # Generate simulation data
    logger.info("Initializing Press Simulator and Pump Optimizer...")
    sim = PressCycleSimulator(dt_seconds=0.2, seed=42)
    df_demand = sim.simulate_fleet_demand(num_cycles=max_cycles)
    opt = PumpStagingOptimizer()
    df_opt = opt.optimize_dataframe(df_demand)

    # Load spot tariff
    tariff_csv = os.path.join(ROOT_DIR, "data", "electricity_prices_es.csv")
    mean_tariff = 64.28
    if os.path.exists(tariff_csv):
        df_tariffs = pd.read_csv(tariff_csv)
        mean_tariff = float(df_tariffs["price_eur_per_mwh"].mean())

    await tag_tariff.write_value(float(mean_tariff), ua.VariantType.Float)

    logger.info(f"OPC-UA Server starting on {endpoint}...")
    async with server:
        logger.info("OPC-UA Server online and listening. Broadcasting telemetry stream...")
        step_dt = 0.2 / playback_speed

        while True:
            for idx, row in df_opt.iterrows():
                # Update Press Telemetry
                await tag_phase.write_value(str(row["phase_name"]), ua.VariantType.String)
                await tag_flow_demand.write_value(float(row["target_flow_lpm"]), ua.VariantType.Float)
                await tag_press_demand.write_value(float(row["target_pressure_bar"]), ua.VariantType.Float)
                await tag_cycle_time.write_value(float(row["timestamp"]), ua.VariantType.Float)
                await tag_cycle_id.write_value(int(row["cycle_id"]), ua.VariantType.Int32)

                # Update Optimizer Staging
                await tag_staging_code.write_value(str(row["opt_staging_code"]), ua.VariantType.String)
                for p_num in [1, 2, 3]:
                    pid = f"pump_{p_num}"
                    await pump_tags[pid]["active"].write_value(bool(row[f"{pid}_active"]), ua.VariantType.Boolean)
                    await pump_tags[pid]["disp_pct"].write_value(float(row[f"{pid}_disp_pct"]), ua.VariantType.Float)
                    await pump_tags[pid]["power_kw"].write_value(float(row[f"{pid}_power_kw"]), ua.VariantType.Float)
                    await pump_tags[pid]["flow_lpm"].write_value(float(row[f"{pid}_flow_lpm"]), ua.VariantType.Float)

                # Power & Financials
                p_opt = float(row["opt_total_power_kw"])
                # Conventional baseline proxy
                p_base = max(p_opt, (row["target_pressure_bar"] * max(152.0, row["target_flow_lpm"])) / 600.0 / 0.85)
                savings_kw = max(0.0, p_base - p_opt)
                savings_eur_hr = (savings_kw / 1000.0) * mean_tariff

                await tag_opt_power.write_value(p_opt, ua.VariantType.Float)
                await tag_base_power.write_value(p_base, ua.VariantType.Float)
                await tag_instant_savings.write_value(savings_eur_hr, ua.VariantType.Float)

                await asyncio.sleep(step_dt)


if __name__ == "__main__":
    try:
        asyncio.run(run_opcua_server())
    except KeyboardInterrupt:
        logger.info("OPC-UA server shutdown requested by user.")
