import streamlit as st
import pandas as pd
import pandapower as pp # Still needed for pp.runpp in reset logic
import numpy as np # Still needed for np.zeros in reset logic

from gads.state_manager_class import StateManager
from gads.attack_manager import (
    ATTACK_BUS_DEFINITIONS,
    ATTACK_TYPES, ATTACK_DESCRIPTIONS
)
from gads.simulation_core import run_simulation_step
from gads.config import NUM_SIMULATION_STEPS # Import NUM_SIMULATION_STEPS

def on_halt_setting_change():
    if st.session_state.halt_on_non_convergence:
        st.toast("Halt on non-convergence: Enabled")
    else:
        st.toast("Halt on non-convergence: Disabled")

def draw_start_reset_buttons(state_manager):
    col_start, col_reset = st.sidebar.columns(2)
    with col_start:
        button_icon = "⏸️" if state_manager.get_is_running() else "▶️"
        st.button(button_icon, key="start_pause", on_click=state_manager.toggle_running, use_container_width=True)
    with col_reset:
        if st.button("🔄", key="reset", use_container_width=True):
            custom_campaign = state_manager.get_custom_campaign()
            state_manager.initialize_session_state(force=True)
            state_manager.set_custom_campaign(custom_campaign)
            st.rerun()

def draw_bus_selection(state_manager):
    st.sidebar.write("Select Bus to Monitor:")
    bus_slider_col, bus_num_col = st.sidebar.columns([3, 1])

    with bus_slider_col:
        st.slider(
            "Bus", 0, len(state_manager.get_net().bus) - 1,
            key="bus_slider",
            on_change=state_manager.sync_bus_from_slider,
            label_visibility="collapsed"
        )
    with bus_num_col:
        st.number_input(
            "Bus", 0, len(state_manager.get_net().bus) - 1,
            key="bus_num_input",
            on_change=state_manager.sync_bus_from_num_input,
            label_visibility="collapsed"
        )

def draw_simulation_speed_slider(state_manager):
    state_manager.set_sim_speed(st.sidebar.slider(
        "Simulation Speed (seconds/step)", 0.01, 1.0, state_manager.get_sim_speed(), 0.01
    ))

def draw_attack_type_selection(state_manager):
    st.sidebar.selectbox(
        "Attack Type",
        ATTACK_TYPES,
        key="attack_type_selector",
        on_change=state_manager.on_attack_type_change,
        index=ATTACK_TYPES.index(state_manager.get_attack_type())
    )
    description = ATTACK_DESCRIPTIONS.get(state_manager.get_attack_type())
    if description:
        st.sidebar.info(description)

def draw_manual_attack_controls(state_manager):
    manual_attack_types = [at for at in ATTACK_TYPES if at not in ["None", "Adaptive Campaign", "Custom Campaign"]]
    if state_manager.get_attack_type() in manual_attack_types:
        # Common controls for most attacks
        if state_manager.get_attack_type() not in ["Line Outage"]:
            st.sidebar.slider(
                "Number of Targets to Attack", 1, 10,
                value=state_manager.get_num_attack_slider(),
                key="num_attack_slider"
            )

        # Attack-specific intensity controls
        if state_manager.get_attack_type() == "Liar Attack":
            state_manager.set_liar_intensity(st.sidebar.slider(
                "Liar Intensity (Voltage Multiplier)", 0.8, 1.2, state_manager.get_liar_intensity(), 0.01
            ))
        elif state_manager.get_attack_type() == "Overload Attack":
            state_manager.set_overload_intensity(st.sidebar.slider(
                "Overload Intensity (Load Multiplier)", 2.0, 10.0, state_manager.get_overload_intensity(), 0.5
            ))
        elif state_manager.get_attack_type() == "Flicker Attack":
            state_manager.set_flicker_intensity(st.sidebar.slider(
                "Flicker Intensity (Load Multiplier)", 2.0, 10.0, state_manager.get_flicker_intensity(), 0.5
            ))
        elif state_manager.get_attack_type() == "Stealth Attack":
            state_manager.set_stealth_intensity(st.sidebar.slider(
                "Stealth Intensity (Voltage Multiplier)", 1.0, 1.05, state_manager.get_stealth_intensity(), 0.005
            ))
        elif state_manager.get_attack_type() == "Ramp Attack":
            state_manager.set_ramp_rate(st.sidebar.slider(
                "Ramp Rate (Load Multiplier Increase per Step)", 0.05, 0.5, state_manager.get_ramp_rate(), 0.05
            ))
        # No specific intensity slider for Line Outage or Data Replay in manual mode yet

def draw_adaptive_campaign_controls(state_manager):
    if state_manager.get_attack_type() == "Adaptive Campaign":
        st.sidebar.slider(
            "Adaptive Campaign Intensity", 1, 10,
            key="adaptive_campaign_intensity_slider",
            value=state_manager.get_adaptive_campaign_intensity(),
            on_change=state_manager.on_intensity_change
        )

        campaign = state_manager.get_generated_adaptive_campaign()
        if campaign:
            st.sidebar.write("Generated Campaign Stages:")
            for i, stage in enumerate(campaign):
                targets = stage.get("buses", stage.get("lines", []))
                target_type = "buses" if "buses" in stage else "lines"
                intensity_info = f" (Intensity: {stage['intensity']:.2f})" if stage['intensity'] != 0 else ""
                stage_info = f"{i+1}: {stage['type']} on {target_type} {targets} from {stage['range'].start}-{stage['range'].stop}{intensity_info}"
                st.sidebar.text(stage_info)

def draw_custom_campaign_builder(state_manager):
    if state_manager.get_attack_type() == "Custom Campaign":
        st.sidebar.subheader("Custom Campaign Builder")
        
        with st.sidebar.expander("Add New Stage", expanded=False):
            with st.form("new_stage_form", clear_on_submit=True):
                campaign_attack_types = [at for at in ATTACK_TYPES if at not in ["None", "Adaptive Campaign", "Custom Campaign"]]
                new_stage_type = st.selectbox("Type", campaign_attack_types)
                
                new_stage_start = st.number_input("Start Step", min_value=0, max_value=95, value=state_manager.get_time_step())
                new_stage_end = st.number_input("End Step", min_value=new_stage_start + 1, max_value=NUM_SIMULATION_STEPS, value=min(new_stage_start + 5, NUM_SIMULATION_STEPS))
                
                new_stage_buses = []
                new_stage_lines = []

                if new_stage_type == "Line Outage":
                    all_lines = list(state_manager.get_net().line.index)
                    default_line = [all_lines[5]] if len(all_lines) > 5 else []
                    new_stage_lines = st.multiselect("Target Lines", all_lines, default=default_line)
                else:
                    all_buses = list(state_manager.get_net().bus.index)
                    default_bus = [all_buses[10]] if len(all_buses) > 10 else []
                    new_stage_buses = st.multiselect("Target Buses", all_buses, default=default_bus)

                new_stage_intensity = 0 # Default value
                if new_stage_type == "Liar Attack":
                    new_stage_intensity = st.slider("Liar Intensity (Voltage Multiplier)", 0.8, 1.2, 1.1, 0.01)
                elif new_stage_type == "Overload Attack":
                    new_stage_intensity = st.slider("Overload Intensity (Load Multiplier)", 2.0, 10.0, 3.0, 0.5)
                elif new_stage_type == "Flicker Attack":
                    new_stage_intensity = st.slider("Flicker Intensity (Load Multiplier)", 2.0, 10.0, 2.0, 0.5)
                elif new_stage_type == "Stealth Attack":
                    new_stage_intensity = st.slider("Stealth Intensity (Voltage Multiplier)", 1.0, 1.05, 1.01, 0.005)
                elif new_stage_type == "Ramp Attack":
                    new_stage_intensity = st.slider("Ramp Rate (Load Multiplier Increase per Step)", 0.05, 0.5, 0.1, 0.05)
                # No intensity for Line Outage or Data Replay

                submitted = st.form_submit_button("Add Stage")
                if submitted:
                    new_stage = {
                        "type": new_stage_type,
                        "range": range(new_stage_start, new_stage_end),
                        "intensity": new_stage_intensity
                    }
                    if new_stage_buses:
                        new_stage["buses"] = new_stage_buses
                    if new_stage_lines:
                        new_stage["lines"] = new_stage_lines

                    custom_campaign = state_manager.get_custom_campaign()
                    custom_campaign.append(new_stage)
                    state_manager.set_custom_campaign(custom_campaign)
                    st.rerun()

        if state_manager.get_custom_campaign():
            st.sidebar.write("Campaign Stages:")
            for i, stage in enumerate(state_manager.get_custom_campaign()):
                targets = stage.get("buses", stage.get("lines", []))
                target_type = "buses" if "buses" in stage else "lines"
                intensity_info = f" (Intensity: {stage['intensity']:.2f})" if stage['intensity'] != 0 else ""
                stage_info = f"{i+1}: {stage['type']} on {target_type} {targets} from {stage['range'].start}-{stage['range'].stop}{intensity_info}"
                st.sidebar.text(stage_info)
                if st.sidebar.button(f"Remove Stage {i+1}", key=f"remove_stage_{i}"):
                    custom_campaign = state_manager.get_custom_campaign()
                    custom_campaign.pop(i)
                    state_manager.set_custom_campaign(custom_campaign)
                    st.rerun()

def draw_sidebar_controls(state_manager):
    draw_start_reset_buttons(state_manager)
    draw_bus_selection(state_manager)
    draw_simulation_speed_slider(state_manager)
    draw_attack_type_selection(state_manager)
    draw_manual_attack_controls(state_manager)
    draw_adaptive_campaign_controls(state_manager)
    draw_custom_campaign_builder(state_manager)
    
    st.sidebar.checkbox(
        "Halt on non-convergence",
        key="halt_on_non_convergence",
        help="If checked, the simulation will pause if a power flow solution does not converge.",
        on_change=on_halt_setting_change
    )
    st.sidebar.caption("Grid Anomaly Detection Simulation")


def run_dashboard():
    # --- Page Setup ---
    st.set_page_config(layout="wide")

    # --- State Management ---
    if "state_manager" not in st.session_state:
        st.session_state.state_manager = StateManager()
        st.session_state.state_manager.initialize_session_state()

    state_manager = st.session_state.state_manager


    draw_sidebar_controls(state_manager)

    # --- Main Content ---
    error_placeholder = st.empty()
    attack_info_placeholder = st.empty()
    col1, col2 = st.columns(2)

    with col1:
        network_plot_placeholder = st.empty()
    with col2:
        st.subheader(f"Voltage at Bus {state_manager.get_selected_bus()}")
        voltage_chart_placeholder = st.empty()

    # --- UI & Simulation Logic ---
    run_simulation_step(error_placeholder, attack_info_placeholder, network_plot_placeholder, voltage_chart_placeholder)

if __name__ == "__main__":
    run_dashboard()