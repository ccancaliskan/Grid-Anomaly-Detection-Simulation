import numpy as np
import pandas as pd
import pandapower as pp
import time

from gads.simulation_state import SimulationState
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks
from gads.plotting import create_interactive_network_plot
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR

def _apply_loads_and_attacks(state: SimulationState):
    """Applies load scaling and physical attacks to the grid."""
    t = state.time_step
    net = state.net
    load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / NUM_SIMULATION_STEPS)
    net.load.p_mw = state.original_loads * load_scaling
    
    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)
    
    net = apply_physical_attacks(state, net, current_attack_type, attacked_buses, attacked_lines, t)
    return is_attacked, current_attack_type, attacked_buses

def _run_power_flow(state: SimulationState):
    """Runs the power flow calculation and returns the true voltage magnitudes."""
    try:
        state.error_message = ""
        pp.runpp(state.net)
        state.is_converged = True
        return state.net.res_bus.vm_pu.copy()
    except pp.LoadflowNotConverged:
        state.error_message = "Load Flow did not converge! Potential blackout scenario."
        state.is_converged = False
        return np.zeros(len(state.net.bus))

def _apply_data_attacks_and_noise(state: SimulationState, true_vm_pu, current_attack_type, attacked_buses):
    """Applies data attacks and noise to the true voltage magnitudes."""
    noisy_vm_pu = true_vm_pu + np.random.normal(0, NOISE_STD_DEV, len(true_vm_pu))
    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, current_attack_type, attacked_buses)
    
    if state.is_converged:
        state.net.res_bus.vm_pu = measured_vm_pu
    return measured_vm_pu

def _store_results(state: SimulationState, measured_vm_pu, is_attacked):
    """Stores the simulation results for the current time step."""
    new_data = pd.DataFrame({
        'time_step': [state.time_step] * len(measured_vm_pu),
        'bus_id': state.net.bus.index,
        'vm_pu': measured_vm_pu,
        'is_attacked': [is_attacked] * len(measured_vm_pu)
    })
    if state.data.empty:
        state.data = new_data
    else:
        state.data = pd.concat([state.data, new_data], ignore_index=True)
    state.voltage_history.append(measured_vm_pu.copy())

def _advance_time_and_check_halt(state: SimulationState):
    """Advances the simulation time step and checks for halt conditions."""
    state.time_step += 1
    if state.time_step >= NUM_SIMULATION_STEPS:
        state.is_running = False

    if state.halt_on_non_convergence and not state.is_converged:
        state.is_running = False

def run_simulation_step(state: SimulationState):
    """
    Executes a single step of the grid anomaly detection simulation.
    This function is intended to be called repeatedly.
    It modifies the state object in place.
    """
    is_attacked, current_attack_type, attacked_buses = _apply_loads_and_attacks(state)
    true_vm_pu = _run_power_flow(state)
    measured_vm_pu = _apply_data_attacks_and_noise(state, true_vm_pu, current_attack_type, attacked_buses)
    _store_results(state, measured_vm_pu, is_attacked)
    _advance_time_and_check_halt(state)
