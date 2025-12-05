
import pandas as pd
import pandapower as pp
from gads.simulation_state import SimulationState
from gads.simulation_core import run_simulation_step

def create_mock_net():
    """Creates a mock pandapower network for testing."""
    net = pp.create_empty_network()
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_bus(net, vn_kv=20.0, name="Bus 2")
    pp.create_bus(net, vn_kv=20.0, name="Bus 3")
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    net.load = pd.DataFrame(columns=['name', 'bus', 'p_mw', 'q_mvar', 'scaling', 'const_z_p_percent', 'const_i_p_percent', 'const_z_q_percent', 'const_i_q_percent', 'in_service'])
    net.load.loc[0] = ['load1', 1, 0.1, 0.05, 1.0, 0.0, 0.0, 0.0, 0.0, True]
    pp.create_ext_grid(net, bus=0, vm_pu=1.0, va_degree=0.0)
    return net

class MockSimulationState(SimulationState):
    def __init__(self):
        super().__init__()
        self.net = create_mock_net()
        # The original_loads are not initialized in the SimulationState constructor,
        # so it is here for the test.
        self.original_loads = self.net.load.p_mw.copy()

def test_run_simulation_step():
    """
    Tests the run_simulation_step function to ensure it updates the state correctly.
    """
    state = MockSimulationState()
    initial_time_step = state.time_step

    run_simulation_step(state)

    assert state.time_step == initial_time_step + 1
    assert not state.data.empty
    assert len(state.voltage_history) == 1
