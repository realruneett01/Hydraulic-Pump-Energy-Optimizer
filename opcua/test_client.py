"""
OPC-UA Verification Client.
Connects to the HPEO Industrial Server, subscribes to press and pump tags,
and prints structured real-time telemetry.
"""

import sys
import asyncio
import logging
from asyncua import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("OPCUA_Client")


class SubHandler:
    """Subscription DataChange Handler for OPC-UA."""

    def datachange_notification(self, node, val, data):
        # Callback for subscribed tag changes
        pass


async def run_client(endpoint: str = "opc.tcp://127.0.0.1:4840/freeopcua/server/",
                     poll_count: int = 15):
    logger.info(f"Connecting to OPC-UA server at {endpoint}...")
    async with Client(url=endpoint) as client:
        logger.info("Connected successfully to HPEO OPC-UA Server.")

        # Discover nodes in namespace
        uri = "http://industrial.automation/hpeo/"
        ns_idx = await client.get_namespace_index(uri)

        root = client.nodes.root
        objects = client.nodes.objects
        hpeo_folder = await objects.get_child([f"{ns_idx}:HPEO_Press_HPU"])

        press_folder = await hpeo_folder.get_child([f"{ns_idx}:PressTelemetry"])
        pump_folder = await hpeo_folder.get_child([f"{ns_idx}:PumpSetpoints"])
        grid_folder = await hpeo_folder.get_child([f"{ns_idx}:EnergyAndTariffs"])

        node_phase = await press_folder.get_child([f"{ns_idx}:PressPhase"])
        node_flow = await press_folder.get_child([f"{ns_idx}:DemandFlow_LPM"])
        node_press = await press_folder.get_child([f"{ns_idx}:DemandPressure_Bar"])
        node_staging = await pump_folder.get_child([f"{ns_idx}:StagingCode"])
        node_power = await grid_folder.get_child([f"{ns_idx}:InstantaneousPower_KW"])
        node_savings = await grid_folder.get_child([f"{ns_idx}:InstantaneousSavings_EUR_hr"])

        print("\n" + "=" * 80)
        print("          HPEO INDUSTRIAL OPC-UA TELEMETRY CLIENT (LIVE MONITOR)")
        print("=" * 80)
        print(f"{'Time':8s} | {'Phase Name':22s} | {'Flow (L/min)':12s} | {'Press (bar)':11s} | {'Staging':9s} | {'Power':8s} | {'Savings':9s}")
        print("-" * 80)

        for i in range(poll_count):
            phase = await node_phase.read_value()
            flow = await node_flow.read_value()
            press = await node_press.read_value()
            staging = await node_staging.read_value()
            power = await node_power.read_value()
            savings = await node_savings.read_value()

            print(f"{i*0.5:6.1f}s  | {phase:22s} | {flow:10.1f}   | {press:9.1f}   | {staging:9s} | {power:6.1f} kW | €{savings:5.2f}/h")
            await asyncio.sleep(0.5)

        print("=" * 80 + "\n")
        logger.info("OPC-UA client verification completed.")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    try:
        asyncio.run(run_client(poll_count=count))
    except Exception as e:
        logger.error(f"Client communication error: {e}")
