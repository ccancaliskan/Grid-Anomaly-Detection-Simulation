# Attack Definitions
# NOTE: ATTACK_BUS_DEFINITIONS was removed — it was never read anywhere in the codebase.
# Targets are chosen dynamically in attack_manager.py and campaign_manager.py.

ATTACK_TYPES = [
    "None",
    "Liar Attack",
    "Overload Attack",
    "Flicker Attack",
    "Stealth Attack",
    "Ramp Attack",
    "Line Outage",
    "Data Replay",
    "Adaptive Campaign",
    "Custom Campaign",
]

ATTACK_DESCRIPTIONS = {
    "Liar Attack": "A data-only attack where a sensor is compromised to send false high or low voltage readings.",
    "Overload Attack": "A physical attack that hijacks high-power devices to create a sudden surge in demand, risking a blackout.",
    "Flicker Attack": "A physical attack that rapidly switches loads on and off, causing annoying voltage fluctuations and instability.",
    "Stealth Attack": "A subtle data attack that slightly alters readings from multiple sensors to mislead operators without triggering simple alarms.",
    "Ramp Attack": "A physical attack that gradually increases power demand over time, making it harder to detect than a sudden overload.",
    "Line Outage": "A physical attack that trips a transmission line, potentially splitting the grid or causing cascading failures.",
    "Data Replay": "A data attack that records legitimate sensor data and replays it later, masking the true state of the grid.",
    "Adaptive Campaign": "An algorithmic attack that automatically switches between different attack types and intensities to maximize disruption.",
    "Custom Campaign": "Build your own multi-stage attack scenario by combining different attacks, targets, and timelines.",
}

# Simulation Parameters
NUM_SIMULATION_STEPS = 96
NOISE_STD_DEV = 0.005
LOAD_SCALE_FACTOR = 0.3  # For sinusoidal load profile
