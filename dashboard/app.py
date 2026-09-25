"""
HPEO - Hydraulic Pump Energy Optimizer
Interactive Executive & Engineering Dashboard (Streamlit).
Designed for Industrial Extrusion Press Automation Demonstration.
"""

import os
import sys

# Ensure workspace root is in python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from simulator.press_demand import PressCycleSimulator
from pumps.pump_model import PumpFleetModel
from optimizer.optimizer import PumpStagingOptimizer
from optimizer.benchmark import StagingBenchmark

# Page Configuration
st.set_page_config(
    page_title="HPEO | Hydraulic Pump Energy Optimizer",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Industrial Dark Theme
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e2638 0%, #151a28 100%);
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .metric-title {
        color: #94a3b8;
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        color: #f8fafc;
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 2px;
    }
    .metric-sub {
        color: #38bdf8;
        font-size: 0.78rem;
        font-weight: 500;
    }
    .badge-industrial {
        background-color: #0284c7;
        color: white;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def load_models():
    fleet = PumpFleetModel()
    opt = PumpStagingOptimizer(fleet_model=fleet)
    benchmark = StagingBenchmark(optimizer=opt)
    return fleet, opt, benchmark


fleet, opt, benchmark = load_models()


# Sidebar Controls
with st.sidebar:
    st.markdown("### ⚙️ Extrusion Press Configuration")
    st.markdown("<span class='badge-industrial'>EXTRUSION PRESS 25 MN</span>", unsafe_allow_html=True)
    st.markdown("")

    alloy = st.selectbox(
        "Aluminum Alloy Recipe",
        ["EN AW-6060 (Architectural - Fast)", "EN AW-6082 (Structural - High Load)", "EN AW-7075 (Aerospace - Heavy)"],
        index=1
    )

    num_cycles = st.slider("Simulated Billet Cycles", min_value=1, max_value=10, value=3, step=1)
    operating_hours = st.number_input("Annual Operating Hours (hrs/yr)", min_value=1000, max_value=8760, value=5500, step=250)

    st.markdown("---")
    st.markdown("### ⚡ Grid & Tariff Scenario")
    tariff_source = st.radio("Electricity Pricing", ["ENTSO-E Spain (ES) Spot Market", "Fixed Industrial Tariff (0.12 €/kWh)"])

    st.markdown("---")
    st.markdown("### 🛠️ HPU Fleet Specifications")
    for spec in fleet.get_pump_specs():
        with st.expander(f"{spec['pump_id'].upper()}: {spec['model']}"):
            st.write(f"**Displacement:** {spec['displacement_cc']:.0f} cc/rev")
            st.write(f"**Max Flow:** {spec['max_flow_lpm']:.1f} L/min")
            st.write(f"**Max Pressure:** {spec['max_pressure_bar']:.0f} bar")
            st.write(f"**Standby Power:** {spec['idle_power_kw']:.1f} kW")


# Run or Cache Simulation
@st.cache_data
def get_simulation_data(num_cycles_val, hours_val):
    sim = PressCycleSimulator(dt_seconds=0.2, seed=42)
    df_demand = sim.simulate_fleet_demand(num_cycles=num_cycles_val)
    res = benchmark.run_benchmark(df_demand, annual_operating_hours=float(hours_val))
    return res


sim_results = get_simulation_data(num_cycles, operating_hours)
summary = sim_results["summary"]
df_res = sim_results["df_results"]


# Title & Header
col_header_1, col_header_2 = st.columns([3, 1])
with col_header_1:
    st.title("Hydraulic Pump Energy Optimizer (HPEO)")
    st.caption("AI/ML Dynamic Staging & Electricity Tariff Optimization for Industrial Extrusion Presses")
with col_header_2:
    st.markdown("<div style='text-align: right; padding-top: 15px;'><span class='badge-industrial'>OT DEMONSTRATOR</span></div>", unsafe_allow_html=True)

# Top KPI Row
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Annual Cost Savings</div>
        <div class="metric-value">€ {summary['annual_financial_savings_eur']:,.0f}</div>
        <div class="metric-sub">at {summary['mean_tariff_eur_mwh']:.1f} €/MWh spot average</div>
    </div>
    """, unsafe_allow_html=True)

with kpi2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Energy Consumption Drop</div>
        <div class="metric-value">-{summary['energy_savings_pct']:.1f}%</div>
        <div class="metric-sub">{summary['annual_saved_kwh']:,.0f} kWh/year avoided</div>
    </div>
    """, unsafe_allow_html=True)

with kpi3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Specific Energy Delta</div>
        <div class="metric-value">{summary['delta_kwh_per_ton']:.1f} <span style='font-size: 1rem;'>kWh/t</span></div>
        <div class="metric-sub">{summary['optimized_kwh_per_ton']:.1f} vs {summary['baseline_kwh_per_ton']:.1f} kWh/t baseline</div>
    </div>
    """, unsafe_allow_html=True)

with kpi4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">CO2 Emissions Avoided</div>
        <div class="metric-value">{summary['annual_co2_saved_tonnes']:.1f} <span style='font-size: 1rem;'>t CO2e</span></div>
        <div class="metric-sub">Spain grid mix factor</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Press Cycle & Staging Timeline",
    "⚡ Pump Fleet Efficiency Surfaces",
    "💶 ENTSO-E Tariffs & ROI Model",
    "📡 Industrial OPC-UA Architecture"
])

# TAB 1: Press Cycle & Staging Timeline
with tab1:
    st.markdown("#### Real-Time Demand Tracking & Optimal Pump Staging")
    st.caption("Demonstrating how HPEO dynamically dispatches only required displacement, avoiding relief bypass losses.")

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "Hydraulic Demand vs. Delivered Flow (L/min) & Pressure (bar)",
            "Active Pump Dispatch & Displacement Fractions (%)",
            "Instantaneous Electrical Power: Baseline vs. HPEO Optimized (kW)"
        ),
        row_heights=[0.35, 0.35, 0.30]
    )

    t = df_res["timestamp"]

    # Subplot 1: Flow and Pressure Demand
    fig.add_trace(go.Scatter(x=t, y=df_res["target_flow_lpm"], name="Demand Flow (L/min)",
                             line=dict(color="#38bdf8", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=df_res["target_pressure_bar"], name="Demand Pressure (bar)",
                             line=dict(color="#f43f5e", width=1.5, dash="dash")), row=1, col=1)

    # Subplot 2: Pump Displacements
    fig.add_trace(go.Scatter(x=t, y=df_res["pump_1_disp_pct"], name="Pump 1 (A4VSO 250)",
                             stackgroup='one', fillcolor="rgba(56, 189, 248, 0.4)", line=dict(color="#38bdf8", width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t, y=df_res["pump_2_disp_pct"], name="Pump 2 (A4VSO 180)",
                             stackgroup='one', fillcolor="rgba(168, 85, 247, 0.4)", line=dict(color="#a855f7", width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t, y=df_res["pump_3_disp_pct"], name="Pump 3 (PV092)",
                             stackgroup='one', fillcolor="rgba(34, 197, 94, 0.4)", line=dict(color="#22c55e", width=1)), row=2, col=1)

    # Subplot 3: Power Comparison
    fig.add_trace(go.Scatter(x=t, y=df_res["base_total_power_kw"], name="Conventional Baseline (kW)",
                             line=dict(color="#ef4444", width=1.5, dash="dot")), row=3, col=1)
    fig.add_trace(go.Scatter(x=t, y=df_res["opt_total_power_kw"], name="HPEO Optimized (kW)",
                             line=dict(color="#10b981", width=2)), row=3, col=1)

    fig.update_layout(
        height=750,
        template="plotly_dark",
        margin=dict(l=40, r=40, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(title_text="Cycle Time (seconds)", row=3, col=1)
    fig.update_yaxes(title_text="Flow / Pressure", row=1, col=1)
    fig.update_yaxes(title_text="Displacement (%)", row=2, col=1)
    fig.update_yaxes(title_text="Power (kW)", row=3, col=1)

    st.plotly_chart(fig, use_container_width=True)


# TAB 2: Pump Fleet Efficiency Surfaces
with tab2:
    st.markdown("#### Surrogate Regression Models Fitted from Manufacturer Datasheets")
    st.caption("2D polynomial efficiency and shaft power maps for Bosch Rexroth A4VSO and Parker PV axial piston pumps.")

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        selected_pump_id = st.selectbox("Select Pump for Detailed Efficiency Mapping", list(fleet.pumps.keys()),
                                        format_func=lambda pid: f"{pid.upper()}: {fleet.pumps[pid].manufacturer} {fleet.pumps[pid].model_name}")

        pump_obj = fleet.pumps[selected_pump_id]

        # Generate meshgrid for contour
        q_grid = np.linspace(20, pump_obj.max_flow_lpm, 30)
        p_grid = np.linspace(30, pump_obj.max_pressure_bar, 30)
        Q_mesh, P_mesh = np.meshgrid(q_grid, p_grid)
        Eta_mesh = np.zeros_like(Q_mesh)
        Power_mesh = np.zeros_like(Q_mesh)

        for i in range(len(p_grid)):
            for j in range(len(q_grid)):
                Eta_mesh[i, j] = pump_obj.predict_efficiency(Q_mesh[i, j], P_mesh[i, j]) * 100.0
                Power_mesh[i, j] = pump_obj.predict_power(Q_mesh[i, j], P_mesh[i, j])

        fig_contour = go.Figure(data=go.Contour(
            z=Eta_mesh,
            x=q_grid,
            y=p_grid,
            colorscale="Viridis",
            colorbar=dict(title="Total Efficiency (%)"),
            contours=dict(coloring='heatmap', showlabels=True)
        ))
        fig_contour.update_layout(
            title=f"Efficiency Surface (%) - {pump_obj.manufacturer} {pump_obj.model_name}",
            xaxis_title="Flow (L/min)",
            yaxis_title="Pressure (bar)",
            template="plotly_dark",
            height=450
        )
        st.plotly_chart(fig_contour, use_container_width=True)

    with col_p2:
        st.markdown("##### Technical Observations on Hydraulic Dispatch")
        st.info(f"""
        **Best Efficiency Point (BEP):**
        - Peak overall efficiency for {pump_obj.model_name} reaches **~91–93%** at 70–95% swashplate angle and 180–260 bar.
        - Operating at <25% displacement drops efficiency below **75%** due to constant friction and leakage losses.
        - **HPEO Advantage:** When flow demand drops during auxiliary phases, HPEO unswashes the large pump entirely, forcing smaller pumps to operate in their high-efficiency regime rather than sharing load at bad angles.
        """)

        # Raw points table
        st.markdown("##### Raw Datasheet Operating Points")
        st.dataframe(pump_obj.raw_data[["flow_lpm", "pressure_bar", "shaft_power_kw", "overall_efficiency"]].head(8),
                     use_container_width=True)


# TAB 3: Dynamic Tariffs & ROI Model
with tab3:
    st.markdown("#### Real ENTSO-E Day-Ahead Electricity Market (Spain ES)")
    st.caption("Spot price integration and industrial investment payback calculator.")

    df_tariffs = pd.read_csv(os.path.join(ROOT_DIR, "data", "electricity_prices_es.csv"))

    fig_tariff = go.Figure()
    fig_tariff.add_trace(go.Scatter(
        x=df_tariffs["timestamp_utc"].tail(168),  # Last 7 days
        y=df_tariffs["price_eur_per_mwh"].tail(168),
        mode="lines",
        line=dict(color="#f59e0b", width=2),
        fill="tozeroy",
        fillcolor="rgba(245, 158, 11, 0.15)",
        name="Day-Ahead Spot Price (€/MWh)"
    ))
    fig_tariff.update_layout(
        title="Spain Bidding Zone (ES) - Day-Ahead Hourly Spot Prices (OMIE / ENTSO-E)",
        xaxis_title="Time (UTC)",
        yaxis_title="Price (€ / MWh)",
        template="plotly_dark",
        height=320,
        margin=dict(l=40, r=40, t=40, b=40)
    )
    st.plotly_chart(fig_tariff, use_container_width=True)

    st.markdown("##### Financial ROI & Payback Calculator")
    roi_col1, roi_col2, roi_col3 = st.columns(3)

    with roi_col1:
        capex_eur = st.number_input("HPEO Edge Controller & Software Modernization Capex (€)", min_value=5000, max_value=80000, value=18000, step=1000)
    with roi_col2:
        num_presses = st.slider("Extrusion Plant Press Fleet Size", min_value=1, max_value=8, value=2, step=1)
    with roi_col3:
        tariff_escalation = st.slider("Annual Energy Cost Inflation (%)", min_value=0.0, max_value=10.0, value=3.0, step=0.5)

    annual_savings_total = summary["annual_financial_savings_eur"] * num_presses
    payback_months = (capex_eur * num_presses / annual_savings_total) * 12.0 if annual_savings_total > 0 else 0.0

    st.success(f"""
    **Projected Financial Return:**
    - **Total Fleet Annual Savings:** € {annual_savings_total:,.2f} / year across {num_presses} press(es).
    - **Estimated Simple Payback Period:** **{payback_months:.1f} months** ({payback_months / 12.0:.1f} years).
    - **10-Year Net Operational Gain:** € {(annual_savings_total * 10 - capex_eur * num_presses):,.2f}
    """)


# TAB 4: Industrial OPC-UA Architecture
with tab4:
    st.markdown("#### Industrial OT Integration Architecture")
    st.markdown("""
    The HPEO system is designed to integrate into industrial press automation and SCADA suites as an advisory or soft-PLC setpoint generator:
    """)

    col_arch1, col_arch2 = st.columns([1, 1])

    with col_arch1:
        st.markdown("""
        ```
        +-----------------------------------------------------------+
        |              Industrial Operator HMI / SCADA              |
        +-----------------------------------------------------------+
                                     ^
                                     |  (OPC-UA / Industrial Ethernet)
                                     v
        +-----------------------------------------------------------+
        |            HPEO Staging & Optimization Engine             |
        |  - Computes MILP pump staging setpoints (<1 ms latency)   |
        |  - Subscribes to ENTSO-E Day-Ahead electricity tariffs    |
        +-----------------------------------------------------------+
                                     ^
                                     |  (IEC 62541 OPC-UA Bridge)
                                     v
        +-----------------------------------------------------------+
        |             Extrusion Press Main PLC (Siemens / Beckhoff) |
        |  - Hard safety interlocks & valve solenoids               |
        |  - High-speed closed-loop ram speed / pressure control    |
        +-----------------------------------------------------------+
                                     |
                                     v
        +-----------------------------------------------------------+
        |        Hydraulic Power Unit (HPU) Pump Manifold           |
        |  - Pump 1: Bosch Rexroth A4VSO 250                        |
        |  - Pump 2: Bosch Rexroth A4VSO 180                        |
        |  - Pump 3: Parker PV092                                   |
        +-----------------------------------------------------------+
        ```
        """)

    with col_arch2:
        st.markdown("##### Standard OPC-UA Node Mapping")
        node_df = pd.DataFrame([
            {"Folder": "PressTelemetry", "Node Tag": "PressPhase", "Type": "String", "Description": "Current cycle phase"},
            {"Folder": "PressTelemetry", "Node Tag": "DemandFlow_LPM", "Type": "Float", "Description": "Hydraulic flow demand (L/min)"},
            {"Folder": "PressTelemetry", "Node Tag": "DemandPressure_Bar", "Type": "Float", "Description": "Hydraulic pressure demand (bar)"},
            {"Folder": "PumpSetpoints", "Node Tag": "StagingCode", "Type": "String", "Description": "Active combination (e.g. P1+P2)"},
            {"Folder": "PumpSetpoints", "Node Tag": "Pump1_DisplacementPct", "Type": "Float", "Description": "Swashplate angle setpoint (0-100%)"},
            {"Folder": "EnergyAndTariffs", "Node Tag": "InstantaneousPower_KW", "Type": "Float", "Description": "Optimized active electrical kW"},
            {"Folder": "EnergyAndTariffs", "Node Tag": "InstantaneousSavings_EUR_hr", "Type": "Float", "Description": "Real-time monetary savings rate"},
        ])
        st.dataframe(node_df, use_container_width=True, hide_index=True)


st.markdown("---")
st.markdown("<div style='text-align: center; color: #64748b; font-size: 0.8rem;'>HPEO Demonstrator | Industrial Extrusion Press Automation Platform</div>", unsafe_allow_html=True)
