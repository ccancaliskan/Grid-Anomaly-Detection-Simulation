import random
from gads.config import NUM_SIMULATION_STEPS

def _get_random_attack_time_range(intensity, total_steps):
    """Generates a random time range for an attack stage."""
    duration = random.randint(max(5, 15 - intensity), max(10, 30 - intensity))
    if total_steps - duration - 1 <= 0:
        start_time = 0
    else:
        start_time = random.randint(0, total_steps - duration - 1)
    end_time = start_time + duration
    return range(start_time, end_time)

def _create_attack_stage(attack_type, time_range, intensity, attackable_buses, attackable_lines):
    """Creates a single attack stage dictionary."""
    stage = {"type": attack_type, "range": time_range}
    
    # Set targets
    if attack_type == "Line Outage":
        if attackable_lines:
            stage["lines"] = random.sample(attackable_lines, min(1, len(attackable_lines)))
        else:
            return None
    else:
        num_targets = random.randint(1, max(2, int(intensity / 2)))
        stage["buses"] = random.sample(attackable_buses, min(num_targets, len(attackable_buses)))

    # Set intensity for relevant attacks
    if attack_type == "Liar Attack":
        stage["intensity"] = random.uniform(1.05, 1.05 + intensity * 0.02)
    elif attack_type == "Overload Attack":
        stage["intensity"] = random.uniform(2.0, 2.0 + intensity * 0.5)
    elif attack_type == "Flicker Attack":
        stage["intensity"] = random.uniform(2.0, 2.0 + intensity * 0.5)
    elif attack_type == "Stealth Attack":
        stage["intensity"] = random.uniform(1.01, 1.01 + intensity * 0.005)
    else:
        stage["intensity"] = 0

    return stage

def generate_adaptive_campaign(intensity, net, total_steps):
    """
    Generates a dynamic, multi-stage attack campaign based on an intensity level.
    """
    campaign = []
    num_attacks = int(intensity * 1.5)
    
    attack_types = ["Liar Attack", "Overload Attack", "Flicker Attack", "Line Outage", "Data Replay"]
    
    attackable_buses = [b for b in net.bus.index if b != 0] # Exclude slack bus
    attackable_lines = list(net.line.index)

    if not attackable_buses:
        return []

    for _ in range(num_attacks):
        attack_type = random.choice(attack_types)
        time_range = _get_random_attack_time_range(intensity, total_steps)
        
        stage = _create_attack_stage(attack_type, time_range, intensity, attackable_buses, attackable_lines)
        if stage:
            campaign.append(stage)
        
    campaign.sort(key=lambda s: s["range"].start)

    return campaign
