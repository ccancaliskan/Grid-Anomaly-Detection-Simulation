import streamlit as st
import random
import pandapower as pp
import numpy as np

from gads.state_manager_class import StateManager
from gads.config import (
    ATTACK_BUS_DEFINITIONS, ADAPTIVE_CAMPAIGN_SCHEDULE,
    ATTACK_TYPES, ATTACK_DESCRIPTIONS
)

state_manager = StateManager()

# --- Attack Logic Functions ---
def determine_attack_status(t):
    """
    Determines the current attack type, targeted buses, and if an attack is active based on the session state.
    """
    is_attacked = 0
    attacked_buses = []
    current_attack_type = state_manager.get_attack_type()

    if current_attack_type == "Adaptive Campaign":
        for step in ADAPTIVE_CAMPAIGN_SCHEDULE:
            if step["range_start"] <= t < step["range_end"]:
                is_attacked = 1
                current_attack_type = step["type"]
                attacked_buses = ATTACK_BUS_DEFINITIONS.get(current_attack_type, [])
                if "intensity_multiplier" in step:
                    if current_attack_type == "Liar Attack": state_manager.set_liar_intensity(state_manager.get_liar_intensity() * step["intensity_multiplier"])
                    elif current_attack_type == "Overload Attack": state_manager.set_overload_intensity(state_manager.get_overload_intensity() * step["intensity_multiplier"])
                    elif current_attack_type == "Flicker Attack": state_manager.set_flicker_intensity(state_manager.get_flicker_intensity() * step["intensity_multiplier"])
                    elif current_attack_type == "Stealth Attack": state_manager.set_stealth_intensity(state_manager.get_stealth_intensity() * step["intensity_multiplier"])
                break
    elif current_attack_type == "Custom Campaign":
        for stage in state_manager.get_custom_campaign():
            if stage["range"].start <= t < stage["range"].stop:
                is_attacked = 1
                current_attack_type = stage["type"]
                attacked_buses = stage["buses"]
                if current_attack_type == "Liar": state_manager.set_liar_intensity(stage["intensity"])
                elif current_attack_type == "Overload": state_manager.set_overload_intensity(stage["intensity"])
                elif current_attack_type == "Flicker": state_manager.set_flicker_intensity(stage["intensity"])
                elif current_attack_type == "Stealth": state_manager.set_stealth_intensity(stage["intensity"])
                elif current_attack_type == "Ramp": state_manager.set_ramp_rate(stage["intensity"])
                break
    elif current_attack_type != "None": # Manual attack
        is_attacked = 1
        if not state_manager.get_current_attack_targets(): # If targets not yet chosen for this attack
            num_to_attack = state_manager.get_num_attacked_buses()
            attackable_buses = [b for b in state_manager.get_net().bus.index if b != 0]
            num_to_attack = min(num_to_attack, len(attackable_buses))
            if num_to_attack > 0:
                state_manager.set_current_attack_targets(random.sample(attackable_buses, num_to_attack))
        attacked_buses = state_manager.get_current_attack_targets()
    
    return is_attacked, current_attack_type, attacked_buses

def apply_physical_attacks(net, attack_type, attacked_buses, t):
    """Applies attacks that physically alter the grid's state before power flow calculation."""
    if attack_type == "Overload Attack":
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state_manager.get_overload_intensity()
    elif attack_type == "Flicker Attack":
        if t % 2 == 0:
            net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state_manager.get_flicker_intensity()
    elif attack_type == "Ramp Attack":
        state_manager.set_ramp_level(state_manager.get_ramp_level() + state_manager.get_ramp_rate())
        net.load.loc[net.load.bus.isin(attacked_buses), 'p_mw'] *= state_manager.get_ramp_level()
    return net

def apply_data_attacks(noisy_vm_pu, attack_type, attacked_buses):
    """Applies attacks that only alter sensor readings after power flow calculation."""
    measured_vm_pu = noisy_vm_pu.copy()
    if attack_type == "Liar Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= state_manager.get_liar_intensity()
    elif attack_type == "Stealth Attack":
        for bus in attacked_buses: measured_vm_pu[bus] *= state_manager.get_stealth_intensity()
    return measured_vm_pu