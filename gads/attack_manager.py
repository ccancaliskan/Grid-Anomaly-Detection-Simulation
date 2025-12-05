import random
import pandapower as pp
import numpy as np

from gads.simulation_state import SimulationState
from gads.config import (
    ATTACK_BUS_DEFINITIONS,
    ATTACK_TYPES, ATTACK_DESCRIPTIONS
)


# --- Attack Logic Functions ---
def _determine_adaptive_campaign_status(state: SimulationState):
    """Determines attack status for an Adaptive Campaign."""
    t = state.time_step
    campaign = state.generated_adaptive_campaign
    for stage in campaign:
        if stage["range"].start <= t < stage["range"].stop:
            is_attacked = 1
            current_attack_type = stage["type"]
            attacked_lines = stage.get("lines", [])
            attacked_buses = stage.get("buses", [])

            if stage['intensity'] != 0:
                if current_attack_type == "Liar Attack": state.liar_intensity = stage["intensity"]
                elif current_attack_type == "Overload Attack": state.overload_intensity = stage["intensity"]
                elif current_attack_type == "Flicker Attack": state.flicker_intensity = stage["intensity"]
                elif current_attack_type == "Stealth Attack": state.stealth_intensity = stage["intensity"]
            
            if current_attack_type == "Data Replay" and t == stage["range"].start:
                if state.voltage_history:
                     state.data_replay_buffer = state.voltage_history[-1]

            return is_attacked, current_attack_type, attacked_buses, attacked_lines
    return 0, state.attack_type, [], []

def _determine_custom_campaign_status(state: SimulationState):
    """Determines attack status for a Custom Campaign."""
    t = state.time_step
    for stage in state.custom_campaign:
        if stage["range"].start <= t < stage["range"].stop:
            is_attacked = 1
            current_attack_type = stage["type"]
            attacked_lines = stage.get("lines", [])
            attacked_buses = stage.get("buses", [])

            if current_attack_type == "Liar Attack": state.liar_intensity = stage["intensity"]
            elif current_attack_type == "Overload Attack": state.overload_intensity = stage["intensity"]
            elif current_attack_type == "Flicker Attack": state.flicker_intensity = stage["intensity"]
            elif current_attack_type == "Stealth Attack": state.stealth_intensity = stage["intensity"]
            elif current_attack_type == "Ramp Attack": state.ramp_rate = stage["intensity"]
            elif current_attack_type == "Data Replay":
                if t == stage["range"].start:
                    if state.voltage_history:
                         state.data_replay_buffer = state.voltage_history[-1]

            return is_attacked, current_attack_type, attacked_buses, attacked_lines
    return 0, state.attack_type, [], []

def _determine_manual_attack_status(state: SimulationState):
    """Determines attack status for a manual attack."""
    is_attacked = 1
    current_attack_type = state.attack_type
    attacked_buses = []
    attacked_lines = []

    if current_attack_type == "Line Outage":
        if not state.current_attack_targets:
            num_to_attack = 1
            attackable_lines = list(state.net.line.index)
            if attackable_lines:
                state.current_attack_targets = random.sample(attackable_lines, num_to_attack)
        attacked_lines = state.current_attack_targets
    else:
        new_num = state.num_attack_slider
        current_targets = state.current_attack_targets
        current_num = len(current_targets)

        if new_num > current_num:
            num_to_add = new_num - current_num
            all_buses = state.net.bus.index
            attackable_buses = [b for b in all_buses if b != 0 and b not in current_targets]
            num_to_add = min(num_to_add, len(attackable_buses))
            if num_to_add > 0:
                new_targets = random.sample(attackable_buses, num_to_add)
                current_targets.extend(new_targets)
                state.current_attack_targets = current_targets
        elif new_num < current_num:
            state.current_attack_targets = current_targets[:new_num]
        
        state.num_attacked_buses = len(state.current_attack_targets)
        attacked_buses = state.current_attack_targets
    
    return is_attacked, current_attack_type, attacked_buses, attacked_lines

def determine_attack_status(state: SimulationState):
    """
    Determines the current attack type, targeted buses/lines, and if an attack is active.
    """
    # Reset ramp level if not a ramp attack
    if state.attack_type != "Ramp Attack":
        state.ramp_level = 1.0

    if state.attack_type == "Adaptive Campaign":
        return _determine_adaptive_campaign_status(state)
    elif state.attack_type == "Custom Campaign":
        return _determine_custom_campaign_status(state)
    elif state.attack_type != "None":
        return _determine_manual_attack_status(state)
    
    return 0, state.attack_type, [], []

def apply_physical_attacks(state: SimulationState, net, attack_type, attacked_buses, attacked_lines, t):
    """Applies attacks that physically alter the grid's state before power flow calculation."""
    if attack_type == "Overload Attack":
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state.overload_intensity
    elif attack_type == "Flicker Attack":
        if t % 2 == 0:
            net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state.flicker_intensity
    elif attack_type == "Ramp Attack":
        state.ramp_level = state.ramp_level + state.ramp_rate
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state.ramp_level
    elif attack_type == "Line Outage":
        if attacked_lines:
            net.line.loc[net.line.index.isin(attacked_lines), 'in_service'] = False
    return net

def apply_data_attacks(state: SimulationState, noisy_vm_pu, attack_type, attacked_buses):
    """Applies attacks that only alter sensor readings after power flow calculation."""
    measured_vm_pu = noisy_vm_pu.copy()
    if attack_type == "Liar Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= state.liar_intensity
    elif attack_type == "Stealth Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= state.stealth_intensity
    elif attack_type == "Data Replay":
        # In campaign mode, this replays a captured buffer.
        # In manual mode, we don't have a capture trigger, so we'll simulate a simple data anomaly.
        attack_mode = state.attack_type
        if attack_mode == "Custom Campaign" or attack_mode == "Adaptive Campaign":
            replay_buffer = state.data_replay_buffer
            if replay_buffer is not None and not replay_buffer.empty:
                for bus in attacked_buses:
                    if bus in replay_buffer.index:
                        measured_vm_pu[bus] = replay_buffer[bus]
        else: # Manual mode placeholder
            for bus in attacked_buses:
                measured_vm_pu[bus] *= 0.8 # Simple anomaly for manual mode
    return measured_vm_pu