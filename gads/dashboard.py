import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import streamlit as st
import numpy as np
import pandas as pd
import pandapower as pp
from gads.simulation import create_ieee_33_bus_system, create_interactive_network_plot
import time
import random

# --- Constants ---
ATTACK_BUS_DEFINITIONS = {
    "Liar Attack": [10],
    "Overload Attack": [15, 16, 17, 18, 19],
    "Flicker Attack": [25],
    "Stealth Attack": [5, 12, 20],
    "Ramp Attack": [28, 29, 30, 31, 32]
}
ADAPTIVE_CAMPAIGN_SCHEDULE = [
    {"type": "Stealth Attack", "range": range(10, 25), "intensity_multiplier": 1.0},
    {"type": "Ramp Attack", "range": range(25, 40)},
    {"type": "Flicker Attack", "range": range(40, 50), "intensity_multiplier": 1.2},
    {"type": "Liar Attack", "range": range(50, 55), "intensity_multiplier": 1.1},
    {"type": "Overload Attack", "range": range(55, 60), "intensity_multiplier": 1.5}
]

# --- Page Setup ---
st.set_page_config(layout="wide")

# --- State Management ---
def initialize_session_state(force=False):
    """Initializes all session state variables if they don't exist or if forced."""
    if not force and "initialized" in st.session_state:
        return
        
    st.session_state.initialized = True
    st.session_state.is_running = False
    st.session_state.time_step = 0
    st.session_state.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu', 'is_attacked'])
    
    net = create_ieee_33_bus_system()
    st.session_state.net = net
    st.session_state.original_loads = net.load.p_mw.copy()
    if net.res_bus.empty:
        pp.runpp(net)

    # UI and Attack State
    st.session_state.attack_type = "None"
    st.session_state.liar_intensity = 1.1
    st.session_state.overload_intensity = 3.0
    st.session_state.flicker_intensity = 2.0
    st.session_state.stealth_intensity = 1.01
    st.session_state.ramp_rate = 0.1
    st.session_state.ramp_level = 1.0
    st.session_state.custom_campaign = []
    st.session_state.error_message = ""
    st.session_state.selected_bus = 0
    st.session_state.bus_slider = 0
    st.session_state.bus_num_input = 0
    st.session_state.sim_speed = 0.1
    st.session_state.num_attacked_buses = 1
    st.session_state.current_attack_targets = []
    st.session_state.num_attack_slider = 1

initialize_session_state()


# --- Sidebar Controls ---
def on_attack_type_change():
    # Callback to update the main attack_type state from the widget's state
    # and handle any side-effects, like resetting the ramp level.
    st.session_state.attack_type = st.session_state.attack_type_selector
    if st.session_state.attack_type != "Ramp Attack":
        st.session_state.ramp_level = 1.0
    st.session_state.current_attack_targets = []

def sync_bus_from_slider():
    st.session_state.selected_bus = st.session_state.bus_slider
    st.session_state.bus_num_input = st.session_state.bus_slider

def sync_bus_from_num_input():
    st.session_state.selected_bus = st.session_state.bus_num_input
    st.session_state.bus_slider = st.session_state.bus_num_input

def on_num_attack_change():
    new_num = st.session_state.num_attack_slider
    current_targets = st.session_state.current_attack_targets
    current_num = len(current_targets)

    if new_num > current_num:
        # We need to add more buses
        num_to_add = new_num - current_num
        # Find buses that are not already targeted and are not the slack bus
        all_buses = st.session_state.net.bus.index
        attackable_buses = [b for b in all_buses if b != 0 and b not in current_targets]
        
        # Ensure we don't try to sample more than what's available
        num_to_add = min(num_to_add, len(attackable_buses))
        
        if num_to_add > 0:
            new_targets = random.sample(attackable_buses, num_to_add)
            st.session_state.current_attack_targets.extend(new_targets)

    elif new_num < current_num:
        # We need to remove buses from the end
        st.session_state.current_attack_targets = current_targets[:new_num]

    # Update the main state variable
    st.session_state.num_attacked_buses = len(st.session_state.current_attack_targets)

# Toggle Start/Pause Button
def toggle_running():
    st.session_state.is_running = not st.session_state.is_running

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

selected_bus = st.session_state.selected_bus

st.session_state.sim_speed = st.sidebar.slider(
    "Simulation Speed (seconds/step)", 0.01, 1.0, 0.1, 0.01
)

# Define attack types
attack_types = ["None", "Liar Attack", "Overload Attack", "Flicker Attack", "Stealth Attack", "Ramp Attack", "Adaptive Campaign", "Custom Campaign"]

# Update attack type from selectbox
st.sidebar.selectbox(
    "Attack Type",
    attack_types,
    key="attack_type_selector",
    on_change=on_attack_type_change,
    index=attack_types.index(st.session_state.attack_type)
)

# Add description box
attack_descriptions = {
    "Liar Attack": "A data-only attack where a sensor is compromised to send false high or low voltage readings.",
    "Overload Attack": "A physical attack that hijacks high-power devices to create a sudden surge in demand, risking a blackout.",
    "Flicker Attack": "A physical attack that rapidly switches loads on and off, causing annoying voltage fluctuations and instability.",
    "Stealth Attack": "A subtle data attack that slightly alters readings from multiple sensors to mislead operators without triggering simple alarms.",
    "Ramp Attack": "A physical attack that gradually increases power demand over time, making it harder to detect than a sudden overload.",
    "Adaptive Campaign": "An algorithmic attack that automatically switches between different attack types and intensities to maximize disruption.",
    "Custom Campaign": "Build your own multi-stage attack scenario by combining different attacks, targets, and timelines."
}

description = attack_descriptions.get(st.session_state.attack_type)
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


# --- Attack Logic Functions ---
def determine_attack_status(t):
    """
    Determines the current attack type, targeted buses, and if an attack is active based on the session state.
    """
    is_attacked = 0
    attacked_buses = []
    current_attack_type = st.session_state.attack_type

    if current_attack_type == "Adaptive Campaign":
        for step in ADAPTIVE_CAMPAIGN_SCHEDULE:
            if t in step["range"]:
                is_attacked = 1
                current_attack_type = step["type"]
                attacked_buses = ATTACK_BUS_DEFINITIONS.get(current_attack_type, [])
                if "intensity_multiplier" in step:
                    if current_attack_type == "Liar Attack": st.session_state.liar_intensity *= step["intensity_multiplier"]
                    elif current_attack_type == "Overload Attack": st.session_state.overload_intensity *= step["intensity_multiplier"]
                    elif current_attack_type == "Flicker Attack": st.session_state.flicker_intensity *= step["intensity_multiplier"]
                    elif current_attack_type == "Stealth Attack": st.session_state.stealth_intensity *= step["intensity_multiplier"]
                break
    elif current_attack_type == "Custom Campaign":
        for stage in st.session_state.custom_campaign:
            if t in stage["range"]:
                is_attacked = 1
                current_attack_type = stage["type"]
                attacked_buses = stage["buses"]
                if current_attack_type == "Liar": st.session_state.liar_intensity = stage["intensity"]
                elif current_attack_type == "Overload": st.session_state.overload_intensity = stage["intensity"]
                elif current_attack_type == "Flicker": st.session_state.flicker_intensity = stage["intensity"]
                elif current_attack_type == "Stealth": st.session_state.stealth_intensity = stage["intensity"]
                elif current_attack_type == "Ramp": st.session_state.ramp_rate = stage["intensity"]
                break
    elif current_attack_type != "None": # Manual attack
        is_attacked = 1
        if not st.session_state.current_attack_targets: # If targets not yet chosen for this attack
            num_to_attack = st.session_state.num_attacked_buses
            attackable_buses = [b for b in st.session_state.net.bus.index if b != 0]
            num_to_attack = min(num_to_attack, len(attackable_buses))
            if num_to_attack > 0:
                st.session_state.current_attack_targets = random.sample(attackable_buses, num_to_attack)
        attacked_buses = st.session_state.current_attack_targets
    
    return is_attacked, current_attack_type, attacked_buses

def apply_physical_attacks(net, attack_type, attacked_buses, t):
    """Applies attacks that physically alter the grid's state before power flow calculation."""
    if attack_type == "Overload Attack":
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= st.session_state.overload_intensity
    elif attack_type == "Flicker Attack":
        if t % 2 == 0:
            net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= st.session_state.flicker_intensity
    elif attack_type == "Ramp Attack":
        st.session_state.ramp_level += st.session_state.ramp_rate
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= st.session_state.ramp_level
    return net

def apply_data_attacks(noisy_vm_pu, attack_type, attacked_buses):
    """Applies attacks that only alter sensor readings after power flow calculation."""
    measured_vm_pu = noisy_vm_pu.copy()
    if attack_type == "Liar Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= st.session_state.liar_intensity
    elif attack_type == "Stealth Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= st.session_state.stealth_intensity
    return measured_vm_pu

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
# Determine attack status for UI (runs even when paused)
is_attacked, current_attack_type, attacked_buses = determine_attack_status(st.session_state.time_step)

# Update UI placeholders (runs even when paused)
if st.session_state.error_message:
    error_placeholder.error(st.session_state.error_message)
else:
    error_placeholder.empty()

if is_attacked:
    attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on buses: {attacked_buses}</h3>", unsafe_allow_html=True)
else:
    attack_info_placeholder.empty()

# Run Simulation Step (only if running)
if st.session_state.is_running:
    t = st.session_state.time_step
    net = st.session_state.net

    # Apply daily load profile
    load_scaling = 1.0 + 0.3 * np.sin(2 * np.pi * t / 96)
    net.load.p_mw = st.session_state.original_loads * load_scaling

    # Apply physical attacks
    net = apply_physical_attacks(net, current_attack_type, attacked_buses, t)
    
    # Run power flow
    try:
        st.session_state.error_message = ""
        pp.runpp(net)
        true_vm_pu = net.res_bus.vm_pu.copy()
    except pp.LoadflowNotConverged:
        st.session_state.error_message = "Load Flow did not converge! Potential blackout scenario."
        true_vm_pu = np.zeros(len(net.bus))
        
    # Apply sensor noise
    noisy_vm_pu = true_vm_pu + np.random.normal(0, 0.005, len(net.bus))

    # Apply data attacks
    measured_vm_pu = apply_data_attacks(noisy_vm_pu, current_attack_type, attacked_buses)
    net.res_bus.vm_pu = measured_vm_pu

    # Store Data
    new_data = pd.DataFrame({
        'time_step': [t] * len(measured_vm_pu),
        'bus_id': net.bus.index,
        'vm_pu': measured_vm_pu,
        'is_attacked': [is_attacked] * len(measured_vm_pu)
    })
    st.session_state.data = pd.concat([st.session_state.data, new_data], ignore_index=True)

    # Advance time
    st.session_state.time_step += 1
    if st.session_state.time_step >= 96:
        st.session_state.is_running = False
        st.success("Simulation finished.")

# --- Display Charts ---
fig = create_interactive_network_plot(st.session_state.net, st.session_state.selected_bus)
network_plot_placeholder.plotly_chart(fig, use_container_width=True)

bus_data = st.session_state.data[st.session_state.data['bus_id'] == st.session_state.selected_bus]
if not bus_data.empty:
    voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])

# Trigger rerun if simulation is active
if st.session_state.is_running:
    time.sleep(st.session_state.sim_speed)
    st.rerun()
