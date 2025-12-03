import random
from gads.config import NUM_SIMULATION_STEPS

def generate_adaptive_campaign(intensity, net, total_steps):
    """
    Generates a dynamic, multi-stage attack campaign based on an intensity level.
    """
    campaign = []
    # More intensity = more frequent and/or more severe attacks
    num_attacks = int(intensity * 1.5)
    
    attack_types = ["Liar Attack", "Overload Attack", "Flicker Attack", "Line Outage", "Data Replay"]
    
    # Get available buses and lines
    attackable_buses = [b for b in net.bus.index if b != 0] # Exclude slack bus
    attackable_lines = list(net.line.index)

    if not attackable_buses:
        return [] # Cannot create attacks without targets

    for i in range(num_attacks):
        attack_type = random.choice(attack_types)
        
        # Ensure attack duration is reasonable
        duration = random.randint(max(5, 15 - intensity), max(10, 30 - intensity))
        
        # Ensure start time is not too close to the end
        if total_steps - duration -1 <= 0:
            start_time = 0
        else:
            start_time = random.randint(0, total_steps - duration - 1)
        
        end_time = start_time + duration
        
        stage = {
            "type": attack_type,
            "range": range(start_time, end_time),
        }

        # Set targets and intensity
        if attack_type == "Line Outage":
            if attackable_lines:
                stage["lines"] = random.sample(attackable_lines, min(1, len(attackable_lines)))
            else:
                continue # Skip if no lines to attack
        else: # Bus-based attacks
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

        campaign.append(stage)
        
    # Sort campaign by start time
    campaign.sort(key=lambda s: s["range"].start)

    return campaign
