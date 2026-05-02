import random
from .config import NUM_SIMULATION_STEPS


def _get_random_attack_time_range(intensity: int, total_steps: int) -> range:
    """Generates a random time range for an attack stage."""
    min_dur = max(5, 15 - intensity)
    max_dur = max(10, 30 - intensity)
    duration = random.randint(min_dur, max_dur)
    max_start = total_steps - duration - 1
    start_time = random.randint(0, max_start) if max_start > 0 else 0
    return range(start_time, start_time + duration)


def _create_attack_stage(
    attack_type: str,
    time_range: range,
    intensity: int,
    attackable_buses: list,
    attackable_lines: list,
) -> dict | None:
    """Creates a single attack stage dictionary. Returns None if targets unavailable."""
    stage: dict = {"type": attack_type, "range": time_range, "intensity": 0}

    # --- Targets ---
    if attack_type == "Line Outage":
        if not attackable_lines:
            return None
        stage["lines"] = random.sample(attackable_lines, min(1, len(attackable_lines)))
        stage["buses"] = []
    else:
        if not attackable_buses:
            return None
        num_targets = random.randint(1, max(2, intensity // 2))
        stage["buses"] = random.sample(attackable_buses, min(num_targets, len(attackable_buses)))
        stage["lines"] = []

    # --- Intensity (only for attacks that use it) ---
    if attack_type == "Liar Attack":
        stage["intensity"] = random.uniform(1.05, 1.05 + intensity * 0.02)
    elif attack_type == "Overload Attack":
        stage["intensity"] = random.uniform(2.0, 2.0 + intensity * 0.5)
    elif attack_type == "Flicker Attack":
        stage["intensity"] = random.uniform(2.0, 2.0 + intensity * 0.5)
    elif attack_type == "Stealth Attack":
        # BUG FIX: original upper bound 1.01 + intensity*0.005 reached only 1.06 at max
        # intensity — too narrow to be meaningful. Widened to match Liar Attack scale.
        stage["intensity"] = random.uniform(0.90, 0.90 - intensity * 0.005)
    # Data Replay, Line Outage → intensity stays 0

    return stage


def generate_adaptive_campaign(intensity: int, net, total_steps: int) -> list[dict]:
    """
    Generates a dynamic, multi-stage attack campaign based on an intensity level.
    Returns a list of stage dicts sorted by start time.
    """
    attack_types = [
        "Liar Attack",
        "Overload Attack",
        "Flicker Attack",
        "Line Outage",
        "Data Replay",
    ]

    # BUG FIX: exclude slack bus (index 0) consistently
    attackable_buses = [b for b in net.bus.index if b != 0]
    attackable_lines = list(net.line.index)

    if not attackable_buses:
        return []

    num_attacks = max(1, int(intensity * 1.5))
    campaign = []

    for _ in range(num_attacks):
        attack_type = random.choice(attack_types)
        time_range = _get_random_attack_time_range(intensity, total_steps)
        stage = _create_attack_stage(
            attack_type, time_range, intensity, attackable_buses, attackable_lines
        )
        if stage:
            campaign.append(stage)

    campaign.sort(key=lambda s: s["range"].start)
    return campaign
