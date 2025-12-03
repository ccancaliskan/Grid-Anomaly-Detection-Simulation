# Attack Definitions
ATTACK_BUS_DEFINITIONS = {
    "Liar Attack": [10],
    "Overload Attack": [15, 16, 17, 18, 19],
    "Flicker Attack": [25],
    "Stealth Attack": [5, 12, 20],
    "Ramp Attack": [28, 29, 30, 31, 32]
}

ADAPTIVE_CAMPAIGN_SCHEDULE = [
    {"type": "Stealth Attack", "range_start": 10, "range_end": 25, "intensity_multiplier": 1.0},
    {"type": "Ramp Attack", "range_start": 25, "range_end": 40},
    {"type": "Flicker Attack", "range_start": 40, "range_end": 50, "intensity_multiplier": 1.2},
    {"type": "Liar Attack", "range_start": 50, "range_end": 55, "intensity_multiplier": 1.1},
    {"type": "Overload Attack", "range_start": 55, "range_end": 60, "intensity_multiplier": 1.5}
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

# Simulation Parameters
NUM_SIMULATION_STEPS = 96
NOISE_STD_DEV = 0.005
LOAD_SCALE_FACTOR = 0.3 # For sinusoidal load profile
