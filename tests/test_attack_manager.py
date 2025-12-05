
import pandas as pd
import pandapower as pp
import numpy as np
import pytest
from gads.simulation_state import SimulationState
from gads.attack_manager import determine_attack_status, apply_physical_attacks, apply_data_attacks

# Helper to create a minimal pandapower network valid for power flow
def create_mock_net_for_attack_manager():
    net = pp.create_empty_network()
    pp.create_bus(net, vn_kv=20.0, name="Bus 0")
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_bus(net, vn_kv=20.0, name="Bus 2")
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_line(net, from_bus=1, to_bus=2, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_ext_grid(net, bus=0, vm_pu=1.0, va_degree=0.0)
    pp.create_load(net, bus=1, p_mw=0.1, q_mvar=0.05)
    
    # Ensure net.load has all necessary columns for runpp and attack application
    if 'load' not in net: # Should not be necessary after pp.create_load but as a fallback
        net.load = pd.DataFrame(columns=['name', 'bus', 'p_mw', 'q_mvar', 'scaling', 'const_z_p_percent', 'const_i_p_percent', 'const_z_q_percent', 'const_i_q_percent', 'in_service', 'type'])
    
    # Add missing pandapower load columns if not present (create_load should add them, but for robustness)
    for col in ['const_z_p_percent', 'const_i_p_percent', 'const_z_q_percent', 'const_i_q_percent', 'scaling', 'in_service', 'type']:
        if col not in net.load.columns:
            if col == 'in_service': net.load[col] = True
            elif col == 'scaling': net.load[col] = 1.0
            elif col == 'type': net.load[col] = 'ind'
            else: net.load[col] = 0.0

    net.original_loads = net.load.p_mw.copy() # Essential for load scaling in simulation
    
    pp.runpp(net) # Run power flow to populate res_bus
    return net

class MockSimulationStateForAttacks(SimulationState):
    def __init__(self):
        super().__init__(grid_type="IEEE 33 Bus") # Use a default grid type that won't trigger file I/O
        self.net = create_mock_net_for_attack_manager()
        self.original_loads = self.net.load.p_mw.copy()
        self.data_replay_buffer = pd.Series([1.0, 0.9, 1.1], index=[0, 1, 2]) # Example replay buffer

def test_determine_attack_status_no_attack():
    """
    Tests the determine_attack_status function when no attack is active.
    """
    state = MockSimulationStateForAttacks()
    state.attack_type = "None"
    state.time_step = 10

    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)

    assert is_attacked == 0
    assert current_attack_type == "None"
    assert attacked_buses == []
    assert attacked_lines == []

def test_determine_attack_status_manual_attack():
    """
    Tests the determine_attack_status function for a manual attack.
    """
    state = MockSimulationStateForAttacks()
    state.attack_type = "Liar Attack"
    state.num_attack_slider = 2
    state.time_step = 10
    state.current_attack_targets = [1, 2]

    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)

    assert is_attacked == 1
    assert current_attack_type == "Liar Attack"
    assert attacked_buses == [1, 2]
    assert attacked_lines == []


#  Tests for apply_physical_attacks 
def test_apply_physical_attacks_overload():
    """Tests applying an Overload Attack."""
    state = MockSimulationStateForAttacks()
    initial_load_p_mw = state.net.load.loc[0, 'p_mw']
    attacked_buses = [1]
    attack_type = "Overload Attack"
    state.overload_intensity = 2.0
    t = 0 # time_step is not directly used for overload intensity

    net_after_attack = apply_physical_attacks(state, state.net, attack_type, attacked_buses, [], t)
    
    # Assert that the load of the attacked bus is multiplied by the intensity
    assert net_after_attack.load.loc[0, 'p_mw'] == initial_load_p_mw * state.overload_intensity

def test_apply_physical_attacks_flicker():
    """Tests applying a Flicker Attack."""
    state = MockSimulationStateForAttacks()
    initial_load_p_mw = state.net.load.loc[0, 'p_mw']
    attacked_buses = [1]
    attack_type = "Flicker Attack"
    state.flicker_intensity = 1.5

    # Test even time step (attack should apply)
    t_even = 0
    net_after_attack_even = apply_physical_attacks(state, state.net, attack_type, attacked_buses, [], t_even)
    assert net_after_attack_even.load.loc[0, 'p_mw'] == initial_load_p_mw * state.flicker_intensity

    # Test odd time step (attack should NOT apply)
    net_for_odd_test = create_mock_net_for_attack_manager() # Reset net state
    state_for_odd_test = MockSimulationStateForAttacks()
    state_for_odd_test.net = net_for_odd_test
    state_for_odd_test.flicker_intensity = 1.5
    t_odd = 1
    net_after_attack_odd = apply_physical_attacks(state_for_odd_test, net_for_odd_test, attack_type, attacked_buses, [], t_odd)
    assert net_after_attack_odd.load.loc[0, 'p_mw'] == initial_load_p_mw # No change

def test_apply_physical_attacks_ramp():
    """Tests applying a Ramp Attack."""
    state = MockSimulationStateForAttacks()
    initial_load_p_mw = state.net.load.loc[0, 'p_mw']
    attacked_buses = [1]
    attack_type = "Ramp Attack"
    state.ramp_rate = 0.1
    state.ramp_level = 1.0 # Initial ramp level

    # Step 1
    t1 = 0
    net_t1 = apply_physical_attacks(state, state.net, attack_type, attacked_buses, [], t1)
    expected_ramp_level_t1 = 1.0 + state.ramp_rate
    assert state.ramp_level == pytest.approx(expected_ramp_level_t1)
    assert net_t1.load.loc[0, 'p_mw'] == pytest.approx(initial_load_p_mw * expected_ramp_level_t1)

    # Step 2 (using the updated state and net from previous step)
    t2 = 1
    # Create a new net state for the second step to properly capture the compounding effect
    net_t2_initial_p_mw = net_t1.load.loc[0, 'p_mw']
    net_t2 = apply_physical_attacks(state, net_t1, attack_type, attacked_buses, [], t2)
    expected_ramp_level_t2 = expected_ramp_level_t1 + state.ramp_rate # This is the state.ramp_level after second call
    assert state.ramp_level == pytest.approx(expected_ramp_level_t2)
    assert net_t2.load.loc[0, 'p_mw'] == pytest.approx(net_t2_initial_p_mw * expected_ramp_level_t2)

def test_apply_physical_attacks_line_outage():
    """Tests applying a Line Outage attack."""
    state = MockSimulationStateForAttacks()
    attacked_lines = [0] # Line between bus 0 and 1
    attack_type = "Line Outage"
    t = 0

    # Ensure line is in service initially
    assert state.net.line.loc[attacked_lines[0], 'in_service'] == True

    net_after_attack = apply_physical_attacks(state, state.net, attack_type, [], attacked_lines, t)
    
    # Assert that the attacked line is taken out of service
    assert net_after_attack.line.loc[attacked_lines[0], 'in_service'] == False

# Tests for apply_data_attacks 
def test_apply_data_attacks_liar():
    """Tests applying a Liar Attack (data)."""
    state = MockSimulationStateForAttacks()
    noisy_vm_pu = pd.Series([1.0, 0.95, 1.05], index=[0, 1, 2])
    attacked_buses = [1]
    attack_type = "Liar Attack"
    state.liar_intensity = 1.1

    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, attack_type, attacked_buses)

    # Attacked bus voltage should be multiplied by liar_intensity
    assert measured_vm_pu[1] == pytest.approx(noisy_vm_pu[1] * state.liar_intensity)
    # Other bus voltages should remain unchanged
    assert measured_vm_pu[0] == pytest.approx(noisy_vm_pu[0])

def test_apply_data_attacks_stealth():
    """Tests applying a Stealth Attack (data)."""
    state = MockSimulationStateForAttacks()
    noisy_vm_pu = pd.Series([1.0, 0.95, 1.05], index=[0, 1, 2])
    attacked_buses = [2]
    attack_type = "Stealth Attack"
    state.stealth_intensity = 1.02

    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, attack_type, attacked_buses)

    # Attacked bus voltage should be multiplied by stealth_intensity
    assert measured_vm_pu[2] == pytest.approx(noisy_vm_pu[2] * state.stealth_intensity)
    # Other bus voltages should remain unchanged
    assert measured_vm_pu[0] == pytest.approx(noisy_vm_pu[0])

def test_apply_data_attacks_data_replay_campaign():
    """Tests applying a Data Replay attack (campaign mode)."""
    state = MockSimulationStateForAttacks()
    noisy_vm_pu = pd.Series([1.0, 0.95, 1.05], index=[0, 1, 2])
    attacked_buses = [1, 2]
    attack_type = "Data Replay"
    state.attack_type = "Adaptive Campaign" # Set attack_type for campaign mode
    # data_replay_buffer is already set in MockSimulationStateForAttacks

    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, attack_type, attacked_buses)

    # Attacked bus voltages should match the replay buffer
    assert measured_vm_pu[1] == pytest.approx(state.data_replay_buffer[1])
    assert measured_vm_pu[2] == pytest.approx(state.data_replay_buffer[2])
    # Other bus voltages should remain unchanged
    assert measured_vm_pu[0] == pytest.approx(noisy_vm_pu[0])

def test_apply_data_attacks_data_replay_manual():
    """Tests applying a Data Replay attack (manual mode)."""
    state = MockSimulationStateForAttacks()
    noisy_vm_pu = pd.Series([1.0, 0.95, 1.05], index=[0, 1, 2])
    attacked_buses = [1]
    attack_type = "Data Replay"
    state.attack_type = "Data Replay" # Set attack_type for manual mode
    state.data_replay_buffer = None # Ensure no buffer is set for manual mode

    measured_vm_pu = apply_data_attacks(state, noisy_vm_pu, attack_type, attacked_buses)

    # Attacked bus voltage should be multiplied by 0.8 in manual mode
    assert measured_vm_pu[1] == pytest.approx(noisy_vm_pu[1] * 0.8)
    # Other bus voltages should remain unchanged
    assert measured_vm_pu[0] == pytest.approx(noisy_vm_pu[0])
