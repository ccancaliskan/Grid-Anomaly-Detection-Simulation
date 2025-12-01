import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import pandas as pd
import pandapower as pp # Still needed for pp.runpp in reset logic
import numpy as np # Still needed for np.zeros in reset logic

from gads.state_manager import (
    initialize_session_state, on_attack_type_change, sync_bus_from_slider,
    sync_bus_from_num_input, on_num_attack_change, toggle_running
)
from gads.attack_manager import (
    ATTACK_BUS_DEFINITIONS, ADAPTIVE_CAMPAIGN_SCHEDULE,
    ATTACK_TYPES, ATTACK_DESCRIPTIONS
)
from gads.simulation_core import run_simulation_step

# --- Page Setup ---
st.set_page_config(layout="wide")

# --- State Management ---
initialize_session_state()

def draw_sidebar_controls():

    # Toggle Start/Pause Button
    col_start, col_reset = st.sidebar.columns(2)
    with col_start:
        button_icon = "⏸️" if st.session_state.is_running else "▶️"
        st.button(button_icon, key="start_pause", on_click=toggle_running, use_container_width=True)
    with col_reset:
        if st.button("🔄", key="reset", use_container_width=True):
            # Preserve custom campaign and rerun
            custom_campaign = st.session_state.custom_campaign
            initialize_session_state(force=True)
            st.session_state.custom_campaign = custom_campaign
            st.rerun()

    st.sidebar.write("Select Bus to Monitor:")
    bus_slider_col, bus_num_col = st.sidebar.columns([3, 1])

    with bus_slider_col:
        st.slider(
            "Bus", 0, len(st.session_state.net.bus) - 1,
            key="bus_slider",
            on_change=sync_bus_from_slider,
            label_visibility="collapsed"
        )
    with bus_num_col:
        st.number_input(
            "Bus", 0, len(st.session_state.net.bus) - 1,
            key="bus_num_input",
            on_change=sync_bus_from_num_input,
            label_visibility="collapsed"
        )

    # selected_bus = st.session_state.selected_bus # This is now handled by the main content

    st.session_state.sim_speed = st.sidebar.slider(
        "Simulation Speed (seconds/step)", 0.01, 1.0, 0.1, 0.01
    )

    # Update attack type from selectbox
    st.sidebar.selectbox(
        "Attack Type",
        ATTACK_TYPES,
        key="attack_type_selector",
        on_change=on_attack_type_change,
        index=ATTACK_TYPES.index(st.session_state.attack_type)
    )

    # Add description box
    description = ATTACK_DESCRIPTIONS.get(st.session_state.attack_type)
    if description:
        st.sidebar.info(description)

    # Show sliders for manual attacks
    if st.session_state.attack_type in ["Liar Attack", "Overload Attack", "Flicker Attack", "Stealth Attack", "Ramp Attack"]:
        st.sidebar.slider(
            "Number of Buses to Attack", 1, 10,
            key="num_attack_slider",
            on_change=on_num_attack_change
        )
        if st.session_state.attack_type == "Liar Attack":
            st.session_state.liar_intensity = st.sidebar.slider(
                "Liar Intensity (Voltage Multiplier)", 0.8, 1.2, st.session_state.liar_intensity, 0.01
            )
        elif st.session_state.attack_type == "Overload Attack":
            st.session_state.overload_intensity = st.sidebar.slider(
                "Overload Intensity (Load Multiplier)", 2.0, 10.0, st.session_state.overload_intensity, 0.5
            )
        elif st.session_state.attack_type == "Flicker Attack":
            st.session_state.flicker_intensity = st.sidebar.slider(
                "Flicker Intensity (Load Multiplier)", 2.0, 10.0, st.session_state.flicker_intensity, 0.5
            )
        elif st.session_state.attack_type == "Stealth Attack":
            st.session_state.stealth_intensity = st.sidebar.slider(
                "Stealth Intensity (Voltage Multiplier)", 1.0, 1.05, st.session_state.stealth_intensity, 0.005
            )
        elif st.session_state.attack_type == "Ramp Attack":
            st.session_state.ramp_rate = st.sidebar.slider(
                "Ramp Rate (Load Multiplier Increase per Step)", 0.05, 0.5, st.session_state.ramp_rate, 0.05
            )
    # UI for Custom Campaign
    elif st.session_state.attack_type == "Custom Campaign":
        st.sidebar.subheader("Custom Campaign Builder")
        
        with st.sidebar.expander("Add New Stage", expanded=False):
            # Using a form to batch inputs
            with st.form("new_stage_form", clear_on_submit=True):
                new_stage_type = st.selectbox("Type", ["Liar", "Overload", "Flicker", "Stealth", "Ramp"])
                new_stage_start = st.number_input("Start Step", min_value=0, max_value=95, value=st.session_state.time_step)
                new_stage_end = st.number_input("End Step", min_value=new_stage_start + 1, max_value=96, value=new_stage_start + 5)
                all_buses = list(st.session_state.net.bus.index)
                default_bus = [all_buses[10]] if all_buses else []
                new_stage_buses = st.multiselect("Target Buses", all_buses, default=default_bus)
                new_stage_intensity = st.number_input("Intensity", value=1.1, step=0.1)
                
                submitted = st.form_submit_button("Add Stage")
                if submitted:
                    st.session_state.custom_campaign.append({
                        "type": new_stage_type,
                        "range": range(new_stage_start, new_stage_end),
                        "buses": new_stage_buses,
                        "intensity": new_stage_intensity
                    })
                    st.rerun()

    if st.session_state.custom_campaign:
        st.sidebar.write("Campaign Stages:")
        for i, stage in enumerate(st.session_state.custom_campaign):
            stage_info = f"{i+1}: {stage['type']} on buses {stage['buses']} from {stage['range'].start}-{stage['range'].stop}"
            st.sidebar.text(stage_info)
            if st.sidebar.button(f"Remove Stage {i+1}", key=f"remove_stage_{i}"):
                st.session_state.custom_campaign.pop(i)
                st.rerun()

    st.sidebar.caption("Grid Anomaly Detection Simulation")

draw_sidebar_controls()

# --- Main Content ---
error_placeholder = st.empty()
attack_info_placeholder = st.empty()
col1, col2 = st.columns(2)

with col1:
    network_plot_placeholder = st.empty()
with col2:
    st.subheader(f"Voltage at Bus {st.session_state.selected_bus}")
    voltage_chart_placeholder = st.empty()

# --- UI & Simulation Logic ---
run_simulation_step(error_placeholder, attack_info_placeholder, network_plot_placeholder, voltage_chart_placeholder)
