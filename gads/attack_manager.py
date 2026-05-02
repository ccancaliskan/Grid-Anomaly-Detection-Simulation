import random

import numpy as np
import pandapower as pp

from .simulation_state import SimulationState
from .config import ATTACK_TYPES


# ---------------------------------------------------------------------------
# Internal helpers — campaign attack-status resolvers
# ---------------------------------------------------------------------------

def _apply_stage_intensity(state: SimulationState, attack_type: str, intensity: float) -> None:
    """Writes intensity for the active stage into the relevant state slot."""
    if intensity == 0:
        return
    if attack_type == "Liar Attack":
        state.liar_intensity = intensity
    elif attack_type == "Overload Attack":
        state.overload_intensity = intensity
    elif attack_type == "Flicker Attack":
        state.flicker_intensity = intensity
    elif attack_type == "Stealth Attack":
        state.stealth_intensity = intensity
    elif attack_type == "Ramp Attack":
        state.ramp_rate = intensity


def _resolve_campaign_stage(
    state: SimulationState, campaign: list[dict]
) -> tuple[int, str, list, list]:
    """
    Generic stage resolver shared by both Adaptive and Custom campaigns.
    Returns (is_attacked, attack_type, attacked_buses, attacked_lines).
    """
    t = state.time_step
    for stage in campaign:
        if stage["range"].start <= t < stage["range"].stop:
            attack_type = stage["type"]
            attacked_buses = stage.get("buses", [])
            attacked_lines = stage.get("lines", [])

            _apply_stage_intensity(state, attack_type, stage.get("intensity", 0))

            # Capture snapshot for Data Replay on the very first tick of the stage
            if attack_type == "Data Replay" and t == stage["range"].start:
                if state.voltage_history:
                    state.data_replay_buffer = state.voltage_history[-1]

            return 1, attack_type, attacked_buses, attacked_lines

    # No active stage
    return 0, state.attack_type, [], []


def _determine_adaptive_campaign_status(
    state: SimulationState,
) -> tuple[int, str, list, list]:
    return _resolve_campaign_stage(state, state.generated_adaptive_campaign)


def _determine_custom_campaign_status(
    state: SimulationState,
) -> tuple[int, str, list, list]:
    return _resolve_campaign_stage(state, state.custom_campaign)


def _determine_manual_attack_status(
    state: SimulationState,
) -> tuple[int, str, list, list]:
    """Determines attack status for a one-shot manual attack."""
    attack_type = state.attack_type
    attacked_buses: list = []
    attacked_lines: list = []

    if attack_type == "Line Outage":
        if not state.current_attack_targets:
            attackable = list(state.net.line.index)
            if attackable:
                state.current_attack_targets = random.sample(attackable, 1)
        attacked_lines = state.current_attack_targets
    else:
        desired = state.num_attack_slider
        current = state.current_attack_targets

        if desired > len(current):
            to_add = desired - len(current)
            candidates = [
                b for b in state.net.bus.index if b != 0 and b not in current
            ]
            to_add = min(to_add, len(candidates))
            if to_add > 0:
                current.extend(random.sample(candidates, to_add))
                state.current_attack_targets = current
        elif desired < len(current):
            state.current_attack_targets = current[:desired]

        state.num_attacked_buses = len(state.current_attack_targets)
        attacked_buses = state.current_attack_targets

    return 1, attack_type, attacked_buses, attacked_lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def determine_attack_status(
    state: SimulationState,
) -> tuple[int, str, list, list]:
    """
    Returns (is_attacked, current_attack_type, attacked_buses, attacked_lines).
    Resets ramp_level whenever the active attack is not a Ramp Attack.
    """
    if state.attack_type != "Ramp Attack":
        state.ramp_level = 1.0

    if state.attack_type == "Adaptive Campaign":
        return _determine_adaptive_campaign_status(state)
    if state.attack_type == "Custom Campaign":
        return _determine_custom_campaign_status(state)
    if state.attack_type != "None":
        return _determine_manual_attack_status(state)

    return 0, state.attack_type, [], []


def apply_physical_attacks(
    state: SimulationState,
    net,
    attack_type: str,
    attacked_buses: list,
    attacked_lines: list,
    t: int,
):
    """Applies attacks that physically alter the grid before power-flow calculation."""
    if attack_type == "Overload Attack":
        net.load.loc[net.load.bus.isin(attacked_buses), "p_mw"] *= state.overload_intensity

    elif attack_type == "Flicker Attack":
        if t % 2 == 0:
            net.load.loc[net.load.bus.isin(attacked_buses), "p_mw"] *= state.flicker_intensity

    elif attack_type == "Ramp Attack":
        state.ramp_level += state.ramp_rate
        net.load.loc[net.load.bus.isin(attacked_buses), "p_mw"] *= state.ramp_level

    elif attack_type == "Line Outage":
        if attacked_lines:
            net.line.loc[net.line.index.isin(attacked_lines), "in_service"] = False

    return net


def apply_data_attacks(
    state: SimulationState,
    noisy_vm_pu,
    attack_type: str,
    attacked_buses: list,
):
    """Applies attacks that alter sensor readings after power-flow calculation."""
    measured = noisy_vm_pu.copy()

    if attack_type == "Liar Attack":
        for bus in attacked_buses:
            measured[bus] *= state.liar_intensity

    elif attack_type == "Stealth Attack":
        for bus in attacked_buses:
            measured[bus] *= state.stealth_intensity

    elif attack_type == "Data Replay":
        # BUG FIX: original code checked state.attack_type (always "Data Replay" here)
        # against campaign strings — that test was always False in manual mode.
        # Now we check whether a captured buffer exists instead.
        buf = state.data_replay_buffer
        if buf is not None and not buf.empty:
            for bus in attacked_buses:
                if bus in buf.index:
                    measured[bus] = buf[bus]
        else:
            # Manual / no-buffer fallback: inject a visible anomaly
            for bus in attacked_buses:
                measured[bus] *= 0.8

    return measured
