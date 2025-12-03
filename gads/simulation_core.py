import numpy as np
import pandas as pd
import pandapower as pp
import time

from gads.simulation_state import SimulationState
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks
from gads.plotting import create_interactive_network_plot
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR

def run_simulation_step(state: SimulationState):
    """
    Executes a single step of the grid anomaly detection simulation.
    This function is intended to be called repeatedly.
    It modifies the state object in place.
    """
    t = state.time_step
    net = state.net

    # Apply loads and attacks
    load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / NUM_SIMULATION_STEPS)
    net.load.p_mw = state.original_loads * load_scaling
    
    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)
    
    net = apply_physical_attacks(state, net, current_attack_type, attacked_buses, attacked_lines, t)

    # Run power flow
    try:
        state.error_message = ""
        pp.runpp(net)
        state.is_converged = True
        true_vm_pu = net.res_bus.vm_pu.copy()
    except pp.LoadflowNotConverged:
        state.error_message = "Load Flow did not converge! Potential blackout scenario."
        state.is_converged = False
        true_vm_pu = np.zeros(len(net.bus))

    # Apply data attacks and noise
    noisy_vm_pu = true_vm_pu + np.random.normal(0, NOISE_STD_DEV, len(true_vm_pu))
    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, current_attack_type, attacked_buses)
    
    if state.is_converged:
        net.res_bus.vm_pu = measured_vm_pu
        
    # Store data
    new_data = pd.DataFrame({
        'time_step': [t] * len(measured_vm_pu),
        'bus_id': net.bus.index,
        'vm_pu': measured_vm_pu,
        'is_attacked': [is_attacked] * len(measured_vm_pu)
    })
    state.data = pd.concat([state.data, new_data], ignore_index=True)
    state.voltage_history.append(measured_vm_pu.copy())

    # Advance time
    state.time_step += 1
    if state.time_step >= NUM_SIMULATION_STEPS:
        state.is_running = False

    # Halt if needed
    if state.halt_on_non_convergence and not state.is_converged:
        state.is_running = False
