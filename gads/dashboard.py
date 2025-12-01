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

# --- Page Setup ---
st.set_page_config(layout="wide")

# --- Session State Initialization ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'time_step' not in st.session_state:
    st.session_state.time_step = 0
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu'])
if 'net' not in st.session_state:
    st.session_state.net = create_ieee_33_bus_system()
    st.session_state.original_loads = st.session_state.net.load.p_mw.copy()
    # Run a power flow to get initial values
    if st.session_state.net.res_bus.empty:
        pp.runpp(st.session_state.net)

# --- Sidebar Controls ---
st.sidebar.title("Grid Anomaly Detection Simulation") # Moved title to sidebar
st.sidebar.markdown("---") # Add a separator for better visual appeal

# Toggle Start/Pause Button
if st.session_state.is_running:
    if st.sidebar.button("Pause", key="pause"):
        st.session_state.is_running = False
else:
    if st.sidebar.button("Start", key="start"):
        st.session_state.is_running = True

if st.sidebar.button("Reset", key="reset"):
    st.session_state.is_running = False
    st.session_state.time_step = 0
    st.session_state.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu'])
    st.session_state.net = create_ieee_33_bus_system()
    st.session_state.original_loads = st.session_state.net.load.p_mw.copy()
    if st.session_state.net.res_bus.empty:
        pp.runpp(st.session_state.net)

st.sidebar.markdown("---") # Add a separator
st.sidebar.subheader("Visualization Settings")
selected_bus = st.sidebar.slider("Select Bus to Monitor", 0, len(st.session_state.net.bus) - 1, 0)

# --- Main Content ---
col1, col2 = st.columns(2)

with col1:
    # Removed "Live Grid Simulation" header
    network_plot_placeholder = st.empty()

with col2:
    st.subheader(f"Voltage at Bus {selected_bus}") # Changed to subheader
    # Removed descriptive text
    voltage_chart_placeholder = st.empty()

# --- Simulation and Visualization ---
net = st.session_state.net

if st.session_state.is_running:
    t = st.session_state.time_step
    
    # Simulate daily load profile
    load_scaling = 1.0 + 0.3 * np.sin(2 * np.pi * t / 96)
    net.load.p_mw = st.session_state.original_loads * load_scaling
    
    # Run power flow
    pp.runpp(net)
    
    # Add noise and store data
    vm_pu = net.res_bus.vm_pu.copy() + np.random.normal(0, 0.005, len(net.bus))
    net.res_bus.vm_pu = vm_pu # Update net with noisy data for visualization
    
    new_data = pd.DataFrame({
        'time_step': [t] * len(vm_pu),
        'bus_id': net.bus.index,
        'vm_pu': vm_pu
    })
    
    st.session_state.data = pd.concat([st.session_state.data, new_data], ignore_index=True)
    
    st.session_state.time_step += 1
    if st.session_state.time_step >= 96:
        st.session_state.is_running = False
        st.success("Simulation finished.")
    
# Display the charts
fig = create_interactive_network_plot(net, selected_bus)
network_plot_placeholder.plotly_chart(fig, use_container_width=True)

bus_data = st.session_state.data[st.session_state.data['bus_id'] == selected_bus]
if not bus_data.empty:
    voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])

if st.session_state.is_running:
    time.sleep(0.1)
    st.rerun()
