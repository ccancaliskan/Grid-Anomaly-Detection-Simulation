import streamlit as st
import numpy as np
import pandas as pd
import pandapower as pp
import time
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks

def run_simulation_step(error_placeholder, attack_info_placeholder, network_plot_placeholder, voltage_chart_placeholder):
    """
    Executes a single step of the grid anomaly detection simulation.
    This function is called repeatedly when the simulation is running.
    """
    t = st.session_state.time_step
    net = st.session_state.net

    # --- Determine Attack Status (runs even when paused) ---
    is_attacked, current_attack_type, attacked_buses = determine_attack_status(t)

    # --- Update UI Placeholders (runs even when paused) ---
    if st.session_state.error_message:
        error_placeholder.error(st.session_state.error_message)
    else:
        error_placeholder.empty()

    if is_attacked:
        attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on buses: {attacked_buses}</h3>", unsafe_allow_html=True)
    else:
        attack_info_placeholder.empty()

    # --- Run Simulation Step (only if running) ---
    if st.session_state.is_running:
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
    from gads.simulation import create_interactive_network_plot # Import here to avoid circular dependency
    fig = create_interactive_network_plot(st.session_state.net, st.session_state.selected_bus)
    network_plot_placeholder.plotly_chart(fig, use_container_width=True)

    bus_data = st.session_state.data[st.session_state.data['bus_id'] == st.session_state.selected_bus]
    if not bus_data.empty:
        voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])

    # Trigger rerun if simulation is active
    if st.session_state.is_running:
        time.sleep(st.session_state.sim_speed)
        st.rerun()