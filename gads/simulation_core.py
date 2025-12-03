from gads.state_manager_class import StateManager
import numpy as np
import pandas as pd
import pandapower as pp
import time
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks
from gads.plotting import create_interactive_network_plot
import streamlit as st # Keep streamlit for st.markdown, st.success, st.error, st.rerun
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR

def _determine_and_display_attack_status(t, attack_info_placeholder):
    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(t)
    if is_attacked:
        if attacked_buses:
            attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on buses: {attacked_buses}</h3>", unsafe_allow_html=True)
        elif attacked_lines:
            attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on lines: {attacked_lines}</h3>", unsafe_allow_html=True)
    else:
        attack_info_placeholder.empty()
    return is_attacked, current_attack_type, attacked_buses, attacked_lines

def _update_error_display(error_placeholder):
    state_manager = st.session_state.state_manager
    if state_manager.get_error_message():
        error_placeholder.error(state_manager.get_error_message())
    else:
        error_placeholder.empty()

def _apply_load_and_attacks(t, net, current_attack_type, attacked_buses, attacked_lines):
    state_manager = st.session_state.state_manager
    load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / NUM_SIMULATION_STEPS)
    net.load.p_mw = state_manager.get_original_loads() * load_scaling
    net = apply_physical_attacks(net, current_attack_type, attacked_buses, attacked_lines, t)
    return net

def _run_power_flow(net):
    state_manager = st.session_state.state_manager
    try:
        state_manager.set_error_message("")
        pp.runpp(net)
        state_manager.set_is_converged(True)
        true_vm_pu = net.res_bus.vm_pu.copy()
    except pp.LoadflowNotConverged:
        state_manager.set_error_message("Load Flow did not converge! Potential blackout scenario.")
        state_manager.set_is_converged(False)
        true_vm_pu = np.zeros(len(net.bus))
    return true_vm_pu

def _apply_noise_and_data_attacks(true_vm_pu, current_attack_type, attacked_buses):
    noisy_vm_pu = true_vm_pu + np.random.normal(0, NOISE_STD_DEV, len(true_vm_pu))
    measured_vm_pu = apply_data_attacks(noisy_vm_pu, current_attack_type, attacked_buses)
    return measured_vm_pu

def _store_simulation_data(t, net, measured_vm_pu, is_attacked):
    state_manager = st.session_state.state_manager
    new_data = pd.DataFrame({
        'time_step': [t] * len(measured_vm_pu),
        'bus_id': state_manager.get_net().bus.index,
        'vm_pu': measured_vm_pu,
        'is_attacked': [is_attacked] * len(measured_vm_pu)
    })
    state_manager.set_data(pd.concat([state_manager.get_data(), new_data], ignore_index=True))
    
    # Store voltage history for data replay attacks
    history = state_manager.get_voltage_history()
    history.append(measured_vm_pu.copy())
    state_manager.set_voltage_history(history)

def _advance_time_and_check_end():
    state_manager = st.session_state.state_manager
    state_manager.set_time_step(state_manager.get_time_step() + 1)
    if state_manager.get_time_step() >= NUM_SIMULATION_STEPS:
        state_manager.set_is_running(False)
        st.success("Simulation finished.")

def _display_charts(network_plot_placeholder, voltage_chart_placeholder):
    state_manager = st.session_state.state_manager
    fig = create_interactive_network_plot(state_manager.get_net(), state_manager.get_selected_bus())
    network_plot_placeholder.plotly_chart(fig, use_container_width=True)

    bus_data = state_manager.get_data()[state_manager.get_data()['bus_id'] == state_manager.get_selected_bus()]
    if not bus_data.empty:
        voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])

def run_simulation_step(error_placeholder, attack_info_placeholder, network_plot_placeholder, voltage_chart_placeholder):
    """
    Executes a single step of the grid anomaly detection simulation.
    This function is called repeatedly when the simulation is running.
    """
    state_manager = st.session_state.state_manager
    t = state_manager.get_time_step()
    net = state_manager.get_net()

    # UI updates that run even when paused
    _update_error_display(error_placeholder)
    is_attacked, current_attack_type, attacked_buses, attacked_lines = _determine_and_display_attack_status(t, attack_info_placeholder)
    _display_charts(network_plot_placeholder, voltage_chart_placeholder)

    # Run simulation step only if running
    if state_manager.get_is_running():
        net = _apply_load_and_attacks(t, net, current_attack_type, attacked_buses, attacked_lines)
        true_vm_pu = _run_power_flow(net)
        measured_vm_pu = _apply_noise_and_data_attacks(true_vm_pu, current_attack_type, attacked_buses)
        if state_manager.get_is_converged():
            net.res_bus.vm_pu = measured_vm_pu
        _store_simulation_data(t, net, measured_vm_pu, is_attacked)
        _advance_time_and_check_end()

        # Halt simulation if non-converged and option is enabled
        if state_manager.get_halt_on_non_convergence() and not state_manager.get_is_converged():
            state_manager.set_is_running(False)
            st.warning("Simulation halted due to power flow non-convergence.")
            
        # Trigger rerun if simulation is active
        time.sleep(state_manager.get_sim_speed())
        st.rerun()