import streamlit as st
import random
import pandapower as pp
import numpy as np

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

ATTACK_TYPES = ["None", "Liar Attack", "Overload Attack", "Flicker Attack", "Stealth Attack", "Ramp Attack", "Adaptive Campaign", "Custom Campaign"]

ATTACK_DESCRIPTIONS = {
    "Liar Attack": "A data-only attack where a sensor is compromised to send false high or low voltage readings.",
    "Overload Attack": "A physical attack that hijacks high-power devices to create a sudden surge in demand, risking a blackout.",
    "Flicker Attack": "A physical attack that rapidly switches loads on and off, causing annoying voltage fluctuations and instability.",
    "Stealth Attack": "A subtle data attack that slightly alters readings from multiple sensors to mislead operators without triggering simple alarms.",
    "Ramp Attack": "A physical attack that gradually increases power demand over time, making it harder to detect than a sudden overload.",
    "Adaptive Campaign": "An algorithmic attack that automatically switches between different attack types and intensities to maximize disruption.",
    "Custom Campaign": "Build your own multi-stage attack scenario by combining different attacks, targets, and timelines."
}

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