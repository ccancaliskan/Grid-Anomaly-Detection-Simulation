import streamlit as st
import pandas as pd
import pandapower as pp # Still needed for pp.runpp in reset logic
import numpy as np # Still needed for np.zeros in reset logic

from gads.state_manager_class import StateManager
from gads.attack_manager import (
    ATTACK_BUS_DEFINITIONS, ADAPTIVE_CAMPAIGN_SCHEDULE,
    ATTACK_TYPES, ATTACK_DESCRIPTIONS
)
from gads.simulation_core import run_simulation_step
from gads.config import NUM_SIMULATION_STEPS # Import NUM_SIMULATION_STEPS

def run_dashboard():
    # --- Page Setup ---
    st.set_page_config(layout="wide")

    # --- State Management ---
    state_manager = StateManager()

    def draw_start_reset_buttons():
        col_start, col_reset = st.sidebar.columns(2)
        with col_start:
            button_icon = "⏸️" if state_manager.get_is_running() else "▶️"
            st.button(button_icon, key="start_pause", on_click=state_manager.toggle_running, use_container_width=True)
        with col_reset:
            if st.button("🔄", key="reset", use_container_width=True):
                custom_campaign = state_manager.get_custom_campaign()
                state_manager._initialize_session_state(force=True)
                state_manager.set_custom_campaign(custom_campaign)
                st.rerun()

    def draw_bus_selection():
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

    def draw_simulation_speed_slider():
        state_manager.set_sim_speed(st.sidebar.slider(
            "Simulation Speed (seconds/step)", 0.01, 1.0, state_manager.get_sim_speed(), 0.01
        ))
        
        # Display convergence status
        if state_manager.get_is_converged():
            st.sidebar.success("Power Flow Converged")
        else:
            st.sidebar.error("Power Flow Not Converged!")

        # Option to halt on non-convergence
        state_manager.set_halt_on_non_convergence(st.sidebar.checkbox(
            "Halt on non-convergence",
            value=state_manager.get_halt_on_non_convergence(),
            help="If checked, the simulation will pause if a power flow solution does not converge."
        ))
        
        # Display convergence status
        if state_manager.get_is_converged():
            st.sidebar.success("Power Flow Converged")
        else:
            st.sidebar.error("Power Flow Not Converged!")

        # Option to halt on non-convergence
        state_manager.set_halt_on_non_convergence(st.sidebar.checkbox(
            "Halt on non-convergence",
            value=state_manager.get_halt_on_non_convergence(),
            help="If checked, the simulation will pause if a power flow solution does not converge."
        ))

    def draw_attack_type_selection():
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

    def draw_manual_attack_controls():
        if state_manager.get_attack_type() in ["Liar Attack", "Overload Attack", "Flicker Attack", "Stealth Attack", "Ramp Attack"]:
            st.sidebar.slider(
                "Number of Buses to Attack", 1, 10,
                key="num_attack_slider",
                on_change=state_manager.on_num_attack_change
            )
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

    def draw_custom_campaign_builder():
        if state_manager.get_attack_type() == "Custom Campaign":
            st.sidebar.subheader("Custom Campaign Builder")
            
            with st.sidebar.expander("Add New Stage", expanded=False):
                with st.form("new_stage_form", clear_on_submit=True):
                    new_stage_type = st.selectbox("Type", ["Liar", "Overload", "Flicker", "Stealth", "Ramp"])
                    new_stage_start = st.number_input("Start Step", min_value=0, max_value=95, value=state_manager.get_time_step())
                    new_stage_end = st.number_input("End Step", min_value=new_stage_start + 1, max_value=NUM_SIMULATION_STEPS, value=min(new_stage_start + 5, NUM_SIMULATION_STEPS))
                    all_buses = list(state_manager.get_net().bus.index)
                    default_bus = [all_buses[10]] if all_buses else []
                    new_stage_buses = st.multiselect("Target Buses", all_buses, default=default_bus)
                    new_stage_intensity = st.number_input("Intensity", value=1.1, step=0.1)
                    
                    submitted = st.form_submit_button("Add Stage")
                    if submitted:
                        custom_campaign = state_manager.get_custom_campaign()
                        custom_campaign.append({
                            "type": new_stage_type,
                            "range": range(new_stage_start, new_stage_end),
                            "buses": new_stage_buses,
                            "intensity": new_stage_intensity
                        })
                        state_manager.set_custom_campaign(custom_campaign)
                        st.rerun()

            if state_manager.get_custom_campaign():
                st.sidebar.write("Campaign Stages:")
                for i, stage in enumerate(state_manager.get_custom_campaign()):
                    stage_info = f"{i+1}: {stage['type']} on buses {stage['buses']} from {stage['range'].start}-{stage['range'].stop}"
                    st.sidebar.text(stage_info)
                    if st.sidebar.button(f"Remove Stage {i+1}", key=f"remove_stage_{i}"):
                        custom_campaign = state_manager.get_custom_campaign()
                        custom_campaign.pop(i)
                        state_manager.set_custom_campaign(custom_campaign)
                        st.rerun()
    def draw_sidebar_controls():
        draw_start_reset_buttons()
        draw_bus_selection()
        draw_simulation_speed_slider()
        draw_attack_type_selection()
        draw_manual_attack_controls()
        draw_custom_campaign_builder()
        st.sidebar.caption("Grid Anomaly Detection Simulation")

    draw_sidebar_controls()

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
