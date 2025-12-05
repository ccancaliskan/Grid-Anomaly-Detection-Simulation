
import pandas as pd
import pandapower as pp
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from gads.simulation import run_time_series_simulation
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR

# Helper to create a minimal pandapower network valid for power flow
def create_minimal_net_for_simulation():
    net = pp.create_empty_network()
    pp.create_bus(net, vn_kv=20.0, name="Bus 0")
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_bus(net, vn_kv=20.0, name="Bus 2")
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_line(net, from_bus=1, to_bus=2, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_ext_grid(net, bus=0, vm_pu=1.0, va_degree=0.0)
    pp.create_load(net, bus=1, p_mw=0.1, q_mvar=0.05)
    
    pp.runpp(net) # Run power flow to populate res_bus
    return net

def test_run_time_series_simulation():
    """
    Tests the run_time_series_simulation function for correct output format and basic functionality.
    """
    net = create_minimal_net_for_simulation()
    num_steps = 5
    noise_std_dev = 0.01

    result_df = run_time_series_simulation(net, num_steps=num_steps, noise_std_dev=noise_std_dev)

    assert isinstance(result_df, pd.DataFrame)
    assert not result_df.empty
    assert list(result_df.columns) == ['time_step', 'bus_id', 'vm_pu']
    assert len(result_df) == num_steps * len(net.bus)

    # Check time steps
    assert sorted(result_df['time_step'].unique()) == list(range(num_steps))

    # Check bus IDs
    assert sorted(result_df['bus_id'].unique()) == list(net.bus.index)

    # Check voltage magnitudes are within a reasonable range (e.g., around 1.0 pu +/- noise)
    assert all(result_df['vm_pu'] > 0.5) # Should not be zero or negative
    assert all(result_df['vm_pu'] < 1.5) # Should not be excessively high

    # Verify that noise has been applied (values are not identical across time steps for the same bus)
    # This is a probabilistic check, so it might fail rarely if noise is exactly zero, but highly unlikely.
    if num_steps > 1:
        # Check that voltage magnitudes for at least one bus vary across time steps due to noise/load scaling
        bus_0_voltages = result_df[result_df['bus_id'] == 0]['vm_pu'].values
        assert not np.all(bus_0_voltages == bus_0_voltages[0])
