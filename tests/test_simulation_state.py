
import pandas as pd
import pandapower as pp
import pytest
from unittest.mock import patch, MagicMock

from gads.simulation_state import SimulationState
from gads.config import NUM_SIMULATION_STEPS, ATTACK_TYPES

# Helper to create a minimal pandapower network for mocking
def create_minimal_net():
    """Creates a mock pandapower network for testing."""
    net = pp.create_empty_network()
    pp.create_bus(net, vn_kv=20.0, name="Bus 0")
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_ext_grid(net, bus=0, vm_pu=1.0, va_degree=0.0)

    # Explicitly create net.load with all expected pandapower load columns
    load_cols = ['name', 'bus', 'p_mw', 'q_mvar', 'const_z_p_percent', 'const_z_q_percent',
                 'const_i_p_percent', 'const_i_q_percent', 'scaling', 'in_service', 'type']
    net.load = pd.DataFrame(columns=load_cols)
    net.load.loc[0] = ['load1', 1, 0.1, 0.05, 0.0, 0.0, 0.0, 0.0, 1.0, True, 'ind']
    net.original_loads = net.load.p_mw.copy()
    return net

@patch('gads.simulation_state.pp.create_empty_network', return_value=create_minimal_net())
@patch('gads.simulation_state.pp.create_bus')
@patch('gads.simulation_state.pp.create_line')
@patch('gads.simulation_state.pp.create_ext_grid')
def test_simulation_state_init(mock_create_ext_grid, mock_create_line,
                               mock_create_bus, mock_create_empty_network):
    """
    Tests the initialization of SimulationState with default values and grid loading.
    """
    state = SimulationState()

    assert state.time_step == 0
    assert state.is_running is False
    assert state.attack_type == "None"
    assert state.selected_bus == 0
    assert isinstance(state.data, pd.DataFrame)
    assert state.data.empty
    assert isinstance(state.net, pp.pandapowerNet)
    assert state.error_message == ""
    assert state.is_converged is True
    assert state.halt_on_non_convergence is False
    assert state.num_attack_slider == 1
    assert state.current_attack_targets == []
    assert state.adaptive_campaign_intensity == 1
    assert state.generated_adaptive_campaign == []
    assert state.generated_adaptive_campaign_intensity == 0
    assert state.liar_intensity == 1.1
    assert state.overload_intensity == 3.0
    assert state.flicker_intensity == 2.0
    assert state.stealth_intensity == 1.01
    assert state.ramp_rate == 0.1
    assert state.ramp_level == 1.0
    assert state.voltage_history == []
    assert state.data_replay_buffer is None
    assert state.custom_campaign == []

@patch('gads.simulation_state.SimulationState._load_osm_grid')
def test_load_grid_custom_grid(mock_load_osm_grid):
    """
    Tests loading a custom grid.
    """
    mock_load_osm_grid.return_value = create_minimal_net()
    state = SimulationState(grid_type="Custom (Uploaded)")
    assert isinstance(state.net, pp.pandapowerNet)
    mock_load_osm_grid.assert_called_once_with("custom_grid")

@patch('gads.simulation_state.generate_adaptive_campaign')
def test_generate_and_store_campaign(mock_generate_adaptive_campaign):
    """
    Tests that generate_and_store_campaign correctly calls the campaign manager
    and stores the result.
    """
    mock_generate_adaptive_campaign.return_value = [{"type": "Liar Attack", "range": range(0, 10)}]
    state = SimulationState()
    state.adaptive_campaign_intensity = 5
    state.generate_and_store_campaign()

    mock_generate_adaptive_campaign.assert_called_once_with(
        state.adaptive_campaign_intensity, state.net, NUM_SIMULATION_STEPS
    )
    assert state.generated_adaptive_campaign == [{"type": "Liar Attack", "range": range(0, 10)}]
    assert state.generated_adaptive_campaign_intensity == 5

# Mocking os.path.exists and subprocess.run for run_importer
@patch('gads.simulation_state.os.path.exists', return_value=True)
@patch('gads.simulation_state.subprocess.run')
@patch('gads.simulation_state.pp.from_excel')
def test_run_importer_success(mock_from_excel, mock_subprocess_run, mock_exists):
    """
    Tests run_importer for a successful import.
    """
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
    mock_from_excel.return_value = create_minimal_net()

    state = SimulationState()
    success, message = state.run_importer("/path/to/osm.pbf", "test_grid")

    mock_subprocess_run.assert_called_once()
    assert success is True
    assert message == "Successfully processed file. Success"

@patch('gads.simulation_state.os.path.exists', return_value=True)
@patch('gads.simulation_state.subprocess.run')
def test_run_importer_failure(mock_subprocess_run, mock_exists):
    """
    Tests run_importer for a failed import.
    """
    import subprocess # Import subprocess for CalledProcessError
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(1, cmd="mock_cmd", stderr="Error during import")

    state = SimulationState()
    success, message = state.run_importer("/path/to/osm.pbf", "test_grid")

    mock_subprocess_run.assert_called_once()
    assert success is False
    assert "An error occurred: Command 'mock_cmd' returned non-zero exit status 1." in message

@patch('gads.simulation_state.os.remove')
@patch('gads.simulation_state.shutil.rmtree')
@patch('gads.simulation_state.os.path.exists')
@patch('gads.simulation_state.pp.from_excel', return_value=create_minimal_net())
def test_delete_osm_grid(mock_from_excel, mock_exists, mock_rmtree, mock_remove):
    """
    Tests deletion of OSM grid data.
    """
    # Simulate grid exists
    mock_exists.side_effect = lambda path: "output.xlsx" in path or "custom_grid" in path

    state = SimulationState() # This will load the default IEEE grid
    state.grid_type = "Custom (Uploaded)" # Manually set to custom for deletion test
    state.delete_osm_grid("custom_grid")

    mock_rmtree.assert_called_once()
    assert "grid-importer/custom_grid" in mock_rmtree.call_args[0][0]

