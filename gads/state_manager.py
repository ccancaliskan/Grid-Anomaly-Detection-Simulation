import streamlit as st
import pandas as pd
import pandapower as pp
from gads.simulation import create_ieee_33_bus_system
import random

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

def on_attack_type_change():
    """Callback to update the main attack_type state from the widget's state and handle side-effects."""
    st.session_state.attack_type = st.session_state.attack_type_selector
    if st.session_state.attack_type != "Ramp Attack":
        st.session_state.ramp_level = 1.0
    st.session_state.current_attack_targets = []

def sync_bus_from_slider():
    """Callback to synchronize bus selection from slider to number input."""
    st.session_state.selected_bus = st.session_state.bus_slider
    st.session_state.bus_num_input = st.session_state.bus_slider

def sync_bus_from_num_input():
    """Callback to synchronize bus selection from number input to slider."""
    st.session_state.selected_bus = st.session_state.bus_num_input
    st.session_state.bus_slider = st.session_state.bus_num_input

def on_num_attack_change():
    """Callback to handle changes in the 'Number of Buses to Attack' slider."""
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

def toggle_running():
    """Callback to toggle the simulation running state."""
    st.session_state.is_running = not st.session_state.is_running
