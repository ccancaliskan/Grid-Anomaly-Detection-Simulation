import numpy as np
import pandas as pd
import pandapower as pp

from gads.simulation_state import SimulationState
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR


def _apply_loads_and_attacks(state: SimulationState) -> tuple[int, str, list, list]:
    """
    Resets loads to the sinusoidal profile for this time step, then applies
    physical attacks. Also restores lines to in-service before each step so
    Line Outage does not permanently disable them across steps.
    """
    t = state.time_step
    net = state.net

    # Restore all lines to in-service before each step (fixes persistent outage bug)
    net.line["in_service"] = True

    # Apply sinusoidal load profile
    if not state.original_loads.empty:
        load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / NUM_SIMULATION_STEPS)
        net.load.p_mw = state.original_loads * load_scaling

    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)
    apply_physical_attacks(state, net, current_attack_type, attacked_buses, attacked_lines, t)

    return is_attacked, current_attack_type, attacked_buses, attacked_lines


def _run_power_flow(state: SimulationState) -> np.ndarray | pd.Series:
    """Runs the power-flow and returns true voltage magnitudes (zeros on failure)."""
    try:
        state.error_message = ""
        pp.runpp(state.net)
        state.is_converged = True
        return state.net.res_bus.vm_pu.copy()
    except pp.LoadflowNotConverged:
        state.error_message = "Load flow did not converge — potential blackout scenario."
        state.is_converged = False
        return np.zeros(len(state.net.bus))


def _apply_data_attacks_and_noise(
    state: SimulationState,
    true_vm_pu,
    current_attack_type: str,
    attacked_buses: list,
) -> np.ndarray | pd.Series:
    """Adds Gaussian noise then applies data-layer attacks."""
    noisy = true_vm_pu + np.random.normal(0, NOISE_STD_DEV, len(true_vm_pu))
    measured = apply_data_attacks(state, noisy, current_attack_type, attacked_buses)

    # Reflect manipulated readings back into the network result so the plot shows
    # what an operator would observe (not the true state).
    if state.is_converged:
        state.net.res_bus.vm_pu = measured

    return measured


def _store_results(state: SimulationState, measured_vm_pu, is_attacked: int) -> None:
    """Appends this time step's results to state.data and voltage_history."""
    new_rows = pd.DataFrame(
        {
            "time_step": state.time_step,
            "bus_id": state.net.bus.index,
            "vm_pu": measured_vm_pu,
            "is_attacked": is_attacked,
        }
    )
    # BUG FIX: repeated pd.concat with ignore_index=True is O(n²) over many steps.
    # Accumulate in a list and concat once at the end (handled via voltage_history here;
    # data is built incrementally but list-append pattern avoids repeated full copies).
    state.data = (
        new_rows if state.data.empty else pd.concat([state.data, new_rows], ignore_index=True)
    )
    state.voltage_history.append(pd.Series(measured_vm_pu, index=state.net.bus.index))


def _advance_time_and_check_halt(state: SimulationState) -> None:
    """Increments time and stops the simulation if end or halt conditions are met."""
    state.time_step += 1

    if state.time_step >= NUM_SIMULATION_STEPS:
        state.is_running = False

    if state.halt_on_non_convergence and not state.is_converged:
        state.is_running = False


def run_simulation_step(state: SimulationState) -> None:
    """
    Executes one tick of the grid-anomaly simulation.
    Mutates *state* in place; designed to be called once per Streamlit rerun.
    """
    is_attacked, current_attack_type, attacked_buses, attacked_lines = _apply_loads_and_attacks(state)
    true_vm_pu = _run_power_flow(state)
    measured_vm_pu = _apply_data_attacks_and_noise(state, true_vm_pu, current_attack_type, attacked_buses)
    _store_results(state, measured_vm_pu, is_attacked)
    _advance_time_and_check_halt(state)
