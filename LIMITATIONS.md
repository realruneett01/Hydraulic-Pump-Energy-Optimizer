# HPEO Technical Limitations & Industrial Edge Cases

This document outlines the real-world physical and operational factors that differentiate this simulation demonstrator from a full brownfield press commissioning project.

---

## 1. Hydraulic Valve Switching & Pressure Dynamics
- **Current Model:** The optimizer commands instantaneous staging transitions between discrete pump configurations at time step boundaries ($\Delta t = 0.1–0.2$ s).
- **Physical Reality:** In high-pressure industrial hydraulics (250–320 bar), switching large directional control or check valves instantaneously induces fluid water hammer and acoustic pressure spikes. 
- **Industrial Remedy:** In a real-world industrial press automation deployment, pump staging setpoints must be ramped through proportional swashplate ramp filters (e.g., 50–150 ms S-curves) with pilot-operated pre-fill valves to prevent hydraulic shock.

---

## 2. Electric Motor Thermal Cycling & Inrush Limits
- **Current Model:** Inactive pumps are modeled in unswashed standby drawing idle power ($P_{\text{idle}} \approx 3–5\%$), or staged off.
- **Physical Reality:** High-power induction motors (160 kW – 250 kW) cannot be started and stopped repeatedly every few seconds. Across-the-line starts or even soft-starters cause severe stator heating, limiting motors to 2–4 cold starts per hour.
- **Industrial Remedy:** Motors remain energized at synchronous speed ($1500$ rpm) while the pump swashplate is unloaded to $0^\circ$ displacement. Full motor de-energization should only occur during prolonged idle windows (e.g., die changes, shift breaks, or pauses exceeding 3 minutes).

---

## 3. High-Pressure Hydraulic Accumulators
- **Current Model:** All instantaneous flow demand is satisfied directly by the active pump fleet.
- **Physical Reality:** Heavy extrusion presses utilize high-pressure nitrogen piston/bladder accumulators to absorb fast transient peaks (e.g., rapid decompression or shear strokes).
- **Industrial Remedy:** The supervisory optimizer should incorporate an accumulator state-of-charge ($SOC$) variable in the MILP objective, scheduling pumps to recharge the accumulator during off-peak auxiliary intervals or low-tariff hours.

---

## 4. Hardware-in-the-Loop (HIL) & Safety Interlocks
- **Current Model:** Python-based async OPC-UA server communicating with simulated tags.
- **Physical Reality:** Direct ram speed and pressure control loops must execute on hard real-time PLCs (IEC 61131-3 on Siemens S7-1500 or Beckhoff TwinCAT 3) with deterministic cycle times of 1–5 ms.
- **Industrial Remedy:** The HPEO optimizer is designed strictly as a **Supervisory Advisory Service (Level 2 Automation)**. It computes and suggests optimal staging setpoints to the PLC over OPC-UA, while the machine PLC retains absolute authority over safety interlocks, over-pressure relief, and closed-loop cylinder position.
