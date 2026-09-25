# Industrial Extrusion Project Implementation Plan: Hydraulic Pump Energy Optimizer (HPEO)
### Industrial AI/ML Demonstrator: Dynamic Pump Staging & Day-Ahead Electricity Tariff Optimization for Hydraulic Extrusion Presses
**Target audience:** Technical Evaluator (Process Automation Lead, Industrial Extrusion) and technical hiring board  
**Timeline:** 3-Day Sprint (Build + Validation + Portfolio Packaging)  
**Author's context:** 4th-year AI/ML Engineering student  
**Project Workspace:** `c:\Users\realr\OneDrive\Desktop\HPEO` (Standalone Repository)

---

## 1. Executive Summary & Industrial Context

Aluminum extrusion presses (15 MN – 50+ MN) are powered by centralized hydraulic power units (HPUs) consisting of multiple high-pressure axial piston pumps (e.g., Bosch Rexroth A4VSO, Parker PV series) connected in parallel to a common manifold. 

### The Problem
During a typical press cycle, hydraulic flow and pressure demands fluctuate drastically:
- **Peak extrusion stroke:** Requires maximum pressure (~250–315 bar) and high flow.
- **Auxiliary phases (billet load, container shift, die slide, shear stroke):** Require moderate flow at low-to-medium pressure.
- **Decompression and idle:** Require minimal holding flow, yet conventional systems frequently keep all pumps spinning at idle, wasting energy through bypass valves, case drain leakage, and circulation friction.
- **Electricity tariff volatility:** European industrial power costs under dynamic day-ahead tariffs (e.g., OMIE / ENTSO-E Spain bidding zone) vary significantly by hour. Rigid pump operating schedules ignore these spot-price fluctuations.

### The Solution: HPEO
A standalone, production-grade demonstrator that implements:
1. **Surrogate Pump Power Models:** Polynomial/regression models fitted from real manufacturer pump performance curves (Bosch Rexroth / Parker), mapping `(flow, pressure) -> electrical power (kW)`.
2. **Self-Contained Press Cycle Demand Simulator:** Physics-informed extrusion press cycle simulation generating realistic hydraulic demand vectors across 6 operational phases.
3. **Constrained Optimization Engine:** Mixed-Integer Linear/Non-Linear Programming (`scipy.optimize`) that dynamically selects the optimal pump combination (on/off staging) and displacement fractions to satisfy demand at minimum total kW.
4. **Tariff-Aware Cost Analytics:** Ingestion of real ENTSO-E day-ahead electricity prices for Spain (ES) to compute hour-by-hour operational expenditure (€), specific energy consumption (kWh/ton), and annualized financial savings.
5. **OT-Ready OPC-UA Server:** An asynchronous OPC-UA server broadcasting optimal pump setpoints and telemetry to simulate direct PLC/SCADA integration.
6. **Executive & Engineering Dashboard:** A multi-view Streamlit application with interactive Gantt staging charts, efficiency heatmaps, real-time demand vs. supply tracking, and financial KPI reporting.

---

## 2. System Architecture

```mermaid
flowchart TD
    subgraph Data["1. Data & Specifications"]
        ENT[ENTSO-E Day-Ahead API<br/>Spain ES Hourly Spot Tariff]
        DS[Pump Datasheets<br/>Rexroth A4VSO / Parker PV]
    end

    subgraph Core["2. Modeling & Simulation"]
        PUMP[Pump Curve Modeling<br/>pumps/pump_model.py<br/>flow + pressure → kW]
        SIM[Press Demand Simulator<br/>simulator/press_demand.py<br/>6-phase extrusion cycle]
    end

    subgraph Engine["3. Optimization & Analytics"]
        OPT[Optimizer Engine<br/>optimizer/optimizer.py<br/>MILP: Min total kW subject to Demand]
        BENCH[Baseline Benchmark<br/>optimizer/benchmark.py<br/>Naive All-On vs. Optimal Staging]
        COST[Cost & Tariff Calculator<br/>data/tariff_client.py<br/>kWh/ton, €/hour, Annual Savings]
    end

    subgraph Integration["4. Industrial OT Bridge"]
        OPC[Async OPC-UA Server<br/>opcua/opcua_server.py<br/>Tags: Staging, Displacements, kW, €]
        CLIENT[Verification Client<br/>opcua/test_client.py]
    end

    subgraph Presentation["5. Executive Dashboard"]
        DASH[Streamlit Interactive App<br/>dashboard/app.py<br/>KPI Cards | Staging Gantt | Efficiency Maps | ROI]
    end

    ENT --> COST
    DS --> PUMP
    PUMP --> OPT
    SIM --> OPT
    OPT --> BENCH
    BENCH --> COST
    OPT --> OPC
    OPC --> CLIENT
    OPT --> DASH
    BENCH --> DASH
    COST --> DASH
```

---

## 3. Standalone Repository Structure

This repository (`HPEO`) is fully self-contained. It does not depend on external repositories or prior project artifacts:

```text
HPEO/
├── data/
│   ├── raw_pump_curves.csv         # Manually/digitized flow, pressure, power points from datasheets
│   ├── electricity_prices_es.csv   # Historical/live Spain day-ahead spot prices (ENTSO-E)
│   ├── fetch_entsoe.py             # Script to fetch real prices from ENTSO-E Transparency API
│   └── mock_tariff_fallback.py     # Deterministic fallback generator if API key is not present
├── simulator/
│   ├── __init__.py
│   └── press_demand.py             # 6-phase press cycle state machine + hydraulic demand model
├── pumps/
│   ├── __init__.py
│   ├── pump_model.py               # Polynomial regression efficiency models for pump fleet
│   └── curve_fit_check.png         # Generated plot validating regression fit against datasheet points
├── optimizer/
│   ├── __init__.py
│   ├── optimizer.py                # Constrained solver (MILP / SciPy) for optimal pump staging
│   └── benchmark.py                # Comparative evaluator: baseline (all-on / naive) vs. optimized
├── opcua/
│   ├── __init__.py
│   ├── opcua_server.py             # Async OPC-UA server publishing staging setpoints & metrics
│   └── test_client.py              # Test subscriber client validating live tag updates
├── dashboard/
│   └── app.py                      # Standalone Streamlit executive & engineering dashboard
├── tests/
│   ├── test_simulator.py           # Unit tests for press cycle phases and demand constraints
│   ├── test_pumps.py               # Unit tests for pump surrogate regression accuracy
│   └── test_optimizer.py           # Unit tests for demand satisfaction and power minimization
├── docs/
│   └── architecture_diagram.png    # Exported visual architecture
├── requirements.txt                # Pinned dependencies
├── README.md                       # Comprehensive showcase & run instructions
└── LIMITATIONS.md                  # Honest technical constraints & industrial calibration notes
```

---

## 4. How to Use This Plan

- Work in strict sequence from **Phase 0** to **Phase 6**.
- Each phase is split into **Agent Tasks** (which can be prompted directly to the coding assistant) and **🧍 Manual Tasks** (which require human judgment, API credentials, or physical review).
- **Rule:** Do not proceed to the next phase until all checks in the **Phase Gate** pass.

---

## 5. Phased Implementation Plan

### Phase 0 — Environment Setup & Data Ingestion

#### Objective
Establish a clean Python 3.11 environment, scaffold the repository, acquire real ENTSO-E electricity spot prices for Spain, and format pump performance data points.

#### Tasks
- **Task 0.1 (agent):**  
  "Create a Python virtual environment configuration and a `requirements.txt` containing:  
  `asyncua>=1.1.5`, `numpy>=1.26.0`, `pandas>=2.2.0`, `scipy>=1.12.0`, `scikit-learn>=1.4.0`, `streamlit>=1.32.0`, `plotly>=5.19.0`, `entsoe-py>=0.5.10`, `requests>=2.31.0`, `matplotlib>=3.8.0`, `pytest>=8.0.0`.  
  Generate the directory structure: `/data`, `/simulator`, `/pumps`, `/optimizer`, `/opcua`, `/dashboard`, `/tests`, `/docs`."

- **Task 0.2 (agent):**  
  "Initialize git repository with an industrial-grade `.gitignore` (venv, `__pycache__`, `.env`, IDE files, OS artifacts)."

- **Task 0.3 (agent):**  
  "In `/data/fetch_entsoe.py`, implement an ENTSO-E client using `entsoe-py` (or direct REST API calls) that accepts an environment variable `ENTSOE_API_KEY` to download hourly Day-Ahead electricity prices for the Spain (`ES`) bidding zone for a specified recent 30-day window, saving the output to `/data/electricity_prices_es.csv` (columns: `timestamp_utc`, `price_eur_per_mwh`, `price_eur_per_kwh`).  
  Implement a deterministic fallback generator `/data/mock_tariff_fallback.py` that generates realistic Spanish industrial Time-of-Use / spot-price diurnal profiles (peak, off-peak, shoulder) if no API key is provided, so the pipeline runs out of the box."

- **Task 0.4 (agent):**  
  "Create `/data/raw_pump_curves.csv` populated with structured manufacturer operating points for a realistic 3-pump press fleet:
  - **Pump 1 (Base Load):** Bosch Rexroth A4VSO 250 (Variable displacement axial piston, displacement 250 cm³/rev, max flow ~375 L/min @ 1500 rpm, max continuous pressure 350 bar).
  - **Pump 2 (Peak Assist):** Bosch Rexroth A4VSO 180 (Displacement 180 cm³/rev, max flow ~270 L/min @ 1500 rpm, max continuous pressure 350 bar).
  - **Pump 3 (Auxiliary / Trim):** Parker PV092 (Displacement 92 cm³/rev, max flow ~138 L/min @ 1500 rpm, max continuous pressure 350 bar).  
  Include operating points across flow (20% to 100%), pressure (50 to 315 bar), and measured shaft power (kW)."

- **🧍 Manual Task 0.5:**  
  (Optional) If you have an ENTSO-E account, export your `ENTSOE_API_KEY` and run `python data/fetch_entsoe.py` to pull fresh real-world data. Review `raw_pump_curves.csv` to ensure nominal parameters match standard industrial datasheets.

#### Phase Gate 0
- [ ] Virtual environment activates cleanly and all packages install without conflict.
- [ ] `electricity_prices_es.csv` contains valid hourly prices (real or realistic fallback).
- [ ] `raw_pump_curves.csv` defines at least 3 distinct pump specifications with valid flow, pressure, and power columns.
- [ ] Initial git commit completed.

---

### Phase 1 — Pump Curve Modeling & Efficiency Surfaces

#### Objective
Transform discrete manufacturer datasheet points into smooth, physics-constrained continuous surrogate models mapping `(flow, pressure) -> power (kW)` for each pump in the fleet.

#### Tasks
- **Task 1.1 (agent):**  
  "In `/pumps/pump_model.py`, build a class `PumpFleetModel` that loads `/data/raw_pump_curves.csv`. For each pump model:
  1. Fit a 2D polynomial regression or regularized surrogate model (order 2) that predicts mechanical/electrical shaft power (kW) from target flow ($Q$, L/min) and pressure ($P$, bar):  
     $$P_{\text{shaft}} = f_i(Q, P)$$
  2. Implement physics bounds: no negative power; zero flow and zero pressure returns minimum standby/circulation idle power ($P_{\text{idle}} \approx 3–5\%$ of nominal).
  3. Expose methods: `get_power(pump_id, flow, pressure)`, `get_efficiency(pump_id, flow, pressure)`, and `get_pump_specs()`."

- **Task 1.2 (agent):**  
  "In `/pumps/pump_model.py`, add a function `generate_fit_verification_plot()` that generates a side-by-side comparison plot of the regression surface vs. the raw datasheet points for each pump, saving it to `/pumps/curve_fit_check.png`."

- **Task 1.3 (agent):**  
  "Write unit tests in `/tests/test_pumps.py` validating that:
  - Predicted power increases monotonically with increasing flow at fixed pressure.
  - Predicted power increases monotonically with increasing pressure at fixed flow.
  - Mean Absolute Percentage Error (MAPE) against raw points is under 5%."

- **🧍 Manual Task 1.4:**  
  Open `/pumps/curve_fit_check.png`. Confirm visually that the fitted surface does not suffer from polynomial Runge oscillations or unrealistic negative slopes within the press operating envelope (50–320 bar, 0–400 L/min).

#### Phase Gate 1
- [ ] All unit tests in `/tests/test_pumps.py` pass.
- [ ] `curve_fit_check.png` generated and verified.
- [ ] Power function returns sane, positive, monotonic values across the full operating range.

---

### Phase 2 — Press Cycle & Hydraulic Demand Simulator

#### Objective
Build a standalone extrusion press cycle generator that models the sequential physical phases of extrusion and produces realistic, time-series hydraulic flow ($Q$) and pressure ($P$) demand curves.

#### Tasks
- **Task 2.1 (agent):**  
  "In `/simulator/press_demand.py`, implement an extrusion press cycle simulator class `PressCycleSimulator` with 6 standard operational phases:
  1. `decompression` (0.8–1.5 s): Rapid pressure release from main cylinder, low flow (~50 L/min), pressure drops from 280 to 20 bar.
  2. `container_shift_open` (2.0–3.5 s): Auxiliary cylinder retracts container, moderate flow (~180 L/min), low pressure (~60 bar).
  3. `shear_stroke` (1.5–2.5 s): Vertical shear cuts discard/butt, high pressure (~210 bar), moderate flow (~140 L/min).
  4. `die_slide_shift` (1.5–2.5 s): Tooling shuttle movement, low flow (~80 L/min), low pressure (~50 bar).
  5. `billet_load_and_seal` (2.5–4.0 s): Loader inserts pre-heated billet, container seals against die, moderate flow (~160 L/min), ramp to seal pressure (~120 bar).
  6. `main_extrusion_stroke` (35.0–70.0 s): Main ram pushes aluminum alloy through die aperture. High pressure (220–300 bar depending on alloy resistance) and high flow (up to 600–750 L/min combined demand during peak speed, tapering during taper-quench phase).

  The simulator must:
  - Support configurable time-step $\Delta t$ (default 0.1 s).
  - Apply realistic Gaussian process noise / jitter to phase durations and hydraulic demand.
  - Output a `pandas.DataFrame` with columns: `timestamp`, `cycle_id`, `phase_name`, `target_flow_lpm`, `target_pressure_bar`, `ram_position_mm`."

- **Task 2.2 (agent):**  
  "In `/simulator/press_demand.py`, add a CLI runner that exports a standard 10-cycle profile to `/data/sample_demand_profile.csv` and generates a summary plot `/simulator/press_demand_profile.png` showing the pressure and flow curves color-coded by phase."

- **Task 2.3 (agent):**  
  "Write unit tests in `/tests/test_simulator.py` checking phase continuity, non-negative pressure/flow values, correct phase ordering, and total cycle duration bounds."

- **🧍 Manual Task 2.4:**  
  Inspect `/simulator/press_demand_profile.png`. Confirm that the extrusion stroke represents ~70–85% of cycle time and dominates hydraulic work, while auxiliary phases exhibit correct low-work signatures.

#### Phase Gate 2
- [ ] All unit tests in `/tests/test_simulator.py` pass.
- [ ] Generated demand profiles reflect true extrusion press duty cycles (clear contrast between main ram extrusion and dead-cycle auxiliary strokes).
- [ ] Demand dataframe schema is locked for consumption by the optimizer.

---

### Phase 3 — Staging Optimization Engine & Baseline Benchmarks

#### Objective
Develop the core mathematical dispatch solver that decides which pumps to turn ON/OFF and what displacement/swashplate fraction to command, minimizing instantaneous electrical kW while strictly meeting or exceeding demand.

#### Tasks
- **Task 3.1 (agent):**  
  "In `/optimizer/optimizer.py`, implement class `PumpStagingOptimizer`:
  - For each time-step with required demand $(Q_{\text{demand}}, P_{\text{demand}})$:
  - Formulate an optimization problem over the pump fleet ($i \in \{1, \dots, N\}$):
    $$\min_{u_i, \alpha_i} \sum_{i=1}^{N} \left[ u_i \cdot P_{\text{shaft}, i}(\alpha_i \cdot Q_{\text{max}, i}, P_{\text{demand}}) + (1 - u_i) \cdot P_{\text{off}} \right]$$
    subject to:
    $$\sum_{i=1}^{N} u_i \cdot \alpha_i \cdot Q_{\text{max}, i} \ge Q_{\text{demand}}$$
    $$\alpha_{\text{min}} \le \alpha_i \le 1.0 \quad \forall i \text{ where } u_i = 1$$
    $$u_i \in \{0, 1\}$$
    where $u_i$ is binary on/off status, and $\alpha_i$ is the swashplate displacement fraction.
  - Implement using `scipy.optimize` (or fast discrete enumeration over all $2^N$ staging combinations with constrained 1D/convex flow allocation, which executes in $<1$ ms per time-step for $N=3$ pumps—ideal for real-time PLC deployment)."

- **Task 3.2 (agent):**  
  "In `/optimizer/benchmark.py`, implement class `StagingBenchmark`:
  - Run the full demand time-series under two strategies:
    1. **Baseline Strategy (Naive / Conventional):** All pumps running continuously ($u_i = 1$). Excess flow beyond demand is dumped through the system main relief valve or recirculated at standby pressure.
    2. **Optimized Strategy (HPEO):** Dynamic staging and proportional displacement. Pumps not needed during auxiliary phases are unswashed to minimum displacement or staged off.
  - Compute total kWh consumed, peak kW demand, specific energy consumption per ton of extruded aluminum (assuming standard 2.7 g/cm³ billet metrics), and percentage energy savings."

- **Task 3.3 (agent):**  
  "In `/optimizer/benchmark.py`, integrate `/data/electricity_prices_es.csv`. Multiply the hourly electrical consumption profiles by the matching hour's spot tariff (€/MWh). Calculate:
  - Daily and annualized energy savings (€/year).
  - CO2 emission reduction (using Spain's grid carbon intensity factor ~0.14 kg CO2e/kWh).
  - Peak-hour tariff avoidance savings (shifting heavy work or unswashing during tariff spikes)."

- **Task 3.4 (agent):**  
  "Write unit tests in `/tests/test_optimizer.py` verifying that:
  - The optimizer never delivers less flow than demanded ($Q_{\text{delivered}} \ge Q_{\text{demand}} - 10^{-3}$).
  - Optimized power (kW) is strictly $\le$ baseline power at every time-step.
  - Solved staging output has valid binary and fractional bounds."

- **🧍 Manual Task 3.5:**  
  Review the benchmark metrics. Sanity-check the energy savings percentage: realistic hydraulic staging savings for press dead-cycle / auxiliary phases typically range from **15% to 32%** of overall hydraulic power unit energy. If the calculated reduction is $>50\%$, verify that the baseline is not artificially inflated with impossible losses.

#### Phase Gate 3
- [ ] All unit tests in `/tests/test_optimizer.py` pass.
- [ ] Benchmark calculates complete energy (kWh) and financial (€) metrics across both strategies.
- [ ] Savings percentage is realistic, defensible, and grounded in hydraulic physics.

---

### Phase 4 — Industrial OPC-UA Server & Telemetry Bridge

#### Objective
Demonstrate operational technology (OT) readiness by implementing an asynchronous OPC-UA server that broadcasts simulated press variables and optimal pump setpoints.

#### Tasks
- **Task 4.1 (agent):**  
  "In `/opcua/opcua_server.py`, build an OPC-UA server using `asyncua` (running on `opc.tcp://127.0.0.1:4840/freeopcua/server/`).
  Expose the following address space under an `HPEO_Press_HPU` folder:
  - **Press Telemetry:** `PressPhase` (String), `DemandFlow_LPM` (Float), `DemandPressure_Bar` (Float), `CycleTime_s` (Float).
  - **Pump Setpoints (Optimizer Output):**
    - `Pump1_Active` (Boolean), `Pump1_DisplacementPct` (Float), `Pump1_PowerKW` (Float)
    - `Pump2_Active` (Boolean), `Pump2_DisplacementPct` (Float), `Pump2_PowerKW` (Float)
    - `Pump3_Active` (Boolean), `Pump3_DisplacementPct` (Float), `Pump3_PowerKW` (Float)
  - **Grid & Financial Tags:** `GridTariff_EUR_MWh` (Float), `InstantaneousPower_KW` (Float), `BaselinePower_KW` (Float), `InstantaneousSavings_EUR_hr` (Float).
  Include an async loop that replays or live-simulates the optimized press cycle, updating all nodes at 5–10 Hz."

- **Task 4.2 (agent):**  
  "In `/opcua/test_client.py`, write a standalone subscription client script that connects to the server, subscribes to data changes on `PressPhase`, `InstantaneousPower_KW`, and `Pump1_Active`, and prints structured telemetry logs to the console."

- **🧍 Manual Task 4.3:**  
  Start `opcua_server.py` in one terminal and `test_client.py` in another. Verify that node values update dynamically in real time and that tag types adhere to standard PLC conventions.

#### Phase Gate 4
- [ ] OPC-UA server initializes and binds cleanly without port collisions.
- [ ] Test client successfully connects, subscribes, and prints live updates.
- [ ] Node namespace contains all designated press, pump, and financial tags.

---

### Phase 5 — Interactive Executive & Engineering Dashboard

#### Objective
Build a high-impact Streamlit web application showcasing both the high-level business case (costs, tariffs, € saved) and the low-level engineering depth (pump staging, efficiency curves, hydraulic tracking).

#### Tasks
- **Task 5.1 (agent):**  
  "In `/dashboard/app.py`, develop a Streamlit dashboard with a dark, modern industrial UI featuring:
  - **Sidebar:** Controls for selecting extrusion recipe (Alloy 6060 vs. 6082 vs. 7075, press tonnage 25 MN, cycle count, electricity tariff scenario [Real Spain Spot vs. Peak/Off-Peak Fixed]).
  - **Top Row - Executive KPI Cards:**
    - Annual Energy Cost Savings (€ / year)
    - Total Energy Reduction (%)
    - Specific Energy Savings ($\Delta$ kWh / ton)
    - Annual CO2 Emissions Avoided (tonnes CO2e)
  - **Tab 1: Live Press Cycle & Staging Timeline:**
    - Synchronized dual Plotly time-series chart showing:
      1. Hydraulic Demand vs. Delivered Flow ($Q$) and Pressure ($P$) with phase background bands.
      2. Pump Staging Timeline (Gantt-style area chart showing which pumps are active and their displacement percentage).
      3. Instantaneous Power: Baseline (kW) vs. Optimized (kW).
  - **Tab 2: Pump Fleet & Efficiency Analysis:**
    - 2D/3D Plotly contour maps of pump efficiency surfaces.
    - Operating point scatter plots showing where each pump operates under the baseline vs. optimized dispatch (demonstrating how the optimizer avoids low-efficiency throttling zones).
  - **Tab 3: Dynamic Tariff & Financial ROI:**
    - Real ENTSO-E Spain electricity price curve for the simulated day.
    - Hourly energy cost (€/h) comparison.
    - Interactive ROI calculator (press annual production volume slider, tariff escalation slider, payback period calculation)."

- **Task 5.2 (agent):**  
  "Ensure the dashboard loads pre-computed benchmark runs instantaneously, while also providing a 'Run Live Simulation' button that triggers the optimizer in real time with progress indication."

- **🧍 Manual Task 5.3:**  
  Run `streamlit run dashboard/app.py`. Check that all visual components render crisply, charts are responsive, numbers match the benchmark outputs from Phase 3, and labels use clear engineering units.

#### Phase Gate 5
- [ ] Dashboard launches without errors.
- [ ] Visual hierarchy is polished and executive-ready.
- [ ] All three tabs function seamlessly with interactive Plotly visuals.
- [ ] Metrics precisely match Phase 3 validation outputs.

---

### Phase 6 — Validation, Packaging & Documentation

#### Objective
Package the project to deliver immediate credibility to Technical Evaluator and the Industrial Extrusion technical evaluation team.

#### Tasks
- **Task 6.1 (agent):**  
  "Generate a professional `README.md` containing:
  1. Executive Summary & Industrial Extrusion Relevance (demonstrating hydraulic domain literacy).
  2. Architecture Diagram (Mermaid).
  3. Key Results Table (Baseline kWh vs. Optimized kWh, % reduction, € savings under Spain ENTSO-E tariffs).
  4. Mathematics of Optimization (formal formulation of the MILP/constrained problem).
  5. Step-by-Step Installation & Quickstart (commands to run the tests, OPC-UA server, and Streamlit dashboard).
  6. Data Transparency Statement detailing what data is real (ENTSO-E spot prices, manufacturer pump curves) vs. simulated (press cycle demand)."

- **Task 6.2 (agent):**  
  "Create `LIMITATIONS.md` outlining genuine industrial edge cases and next steps:
  - Hydraulic valve switching dynamics and shock dampening (pressure spikes during sudden staging).
  - Pump motor start/stop cycle life constraints (minimum run times and restart dwell times).
  - Accumulator circuit integration (how high-pressure bottles affect staging).
  - Hardware-in-the-Loop (HIL) calibration on real Siemens S7-1500 / Beckhoff TwinCAT PLCs."

- **🧍 Manual Task 6.3:**  
  Review both documents. Ensure the voice is authentic to an ambitious 4th-year engineering student. Test cloning into a clean folder or running from a fresh shell to confirm zero missing dependencies. Commit and push to GitHub.

#### Phase Gate 6
- [ ] `README.md` and `LIMITATIONS.md` are complete, technically thorough, and professionally written.
- [ ] Complete pipeline runs cleanly from a fresh terminal.
- [ ] GitHub repository is public and documented.

---

## 6. Consolidated Manual-Intervention Checklist

| # | Task | Objective / Rationale |
|---|---|---|
| **1** | Environment Verification | Confirm Python 3.11 virtual environment and all packages install cleanly on your OS. |
| **2** | ENTSO-E Credentials (Optional) | Add real API token if available, or confirm fallback tariff generates sane values. |
| **3** | Datasheet Parameter Check | Review `raw_pump_curves.csv` against public Bosch Rexroth / Parker specifications. |
| **4** | Curve Fit Visual Inspection | Inspect `/pumps/curve_fit_check.png` to guarantee no polynomial overfitting or negative power. |
| **5** | Demand Profile Validation | Check `/simulator/press_demand_profile.png` to confirm realistic cycle phase proportions. |
| **6** | Benchmark Savings Sanity Check | Confirm energy savings fall within the defensible industrial range (15%–32%). |
| **7** | OPC-UA Live Verification | Verify simultaneous execution of server and client in terminal windows. |
| **8** | Dashboard Polish Review | Verify visual aesthetic, interactive charts, and formatting in Streamlit. |
| **9** | Document Review & Git Push | Read `README.md` and `LIMITATIONS.md`, commit code, and push to GitHub. |

---

## 7. Interview Talking Points & Defense Strategy (for Industrial Extrusion)

When presenting this project to technical evaluators or the automation team, emphasize the following engineering concepts:

1. **Why variable displacement pump staging matters:**  
   *"Variable displacement swashplate pumps are efficient near full displacement, but volumetric and mechanical efficiency drops sharply when running at 10–20% swashplate angle under high pressure. Staging off or unswashing unnecessary pumps allows the remaining active pumps to operate near their Best Efficiency Point (BEP)."*

2. **Why not just use Variable Frequency Drives (VFDs) on all pumps?**  
   *"While VFDs modulate electric motor RPM, large axial piston pumps (e.g. 250 cm³) have minimum speed limits for hydrostatic bearing lubrication (~400–600 rpm). A hybrid approach combining swashplate displacement control with dynamic pump staging provides superior dynamic response (<50 ms) compared to motor inertial spin-up times."*

3. **Solver Latency & Real-Time Viability:**  
   *"For a 3–4 pump system, the discrete combinatorial space ($2^N$) is small enough that our optimal dispatch evaluates in under 1 millisecond on standard industrial PCs (e.g., Beckhoff IPC or Siemens IPC), making it fully compatible with 50 ms or 100 ms PLC supervisory control cycles."*

4. **Integration via Standards (OPC-UA):**  
   *"The optimizer is designed as an Edge advisory service or soft-PLC module communicating over OPC-UA with the machine PLC (IEC 61131-3), keeping safety-critical interlocks on the PLC while delegating setpoint optimization to Python."*
