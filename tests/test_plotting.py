
import pandas as pd
import pandapower as pp
import plotly.graph_objects as go
import pytest

from gads.plotting import create_interactive_network_plot

# Helper to create a minimal pandapower network for mocking
def create_minimal_net_for_plotting():
    net = pp.create_empty_network()
    # Add buses with geodata
    pp.create_bus(net, vn_kv=20.0, name="Bus 0")
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_bus(net, vn_kv=20.0, name="Bus 2")

    # Manually set bus_geodata for the created buses
    net.bus_geodata = pd.DataFrame(
        [[10, 20], [30, 40], [50, 60]],
        index=[0, 1, 2],
        columns=['x', 'y']
    )

    # Add lines
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    pp.create_line(net, from_bus=1, to_bus=2, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")

    # Add an external grid for slack bus
    pp.create_ext_grid(net, bus=0, vm_pu=1.0, va_degree=0.0)
    # Add a load
    pp.create_load(net, bus=1, p_mw=0.1, q_mvar=0.05)
    
    # Run power flow to populate net.res_bus
    pp.runpp(net)

    return net

def test_create_interactive_network_plot():
    """
    Tests the create_interactive_network_plot function to ensure it returns a valid Plotly figure
    with expected traces.
    """
    net = create_minimal_net_for_plotting()
    
    fig = create_interactive_network_plot(net)

    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0

    # Check for line traces (2 lines and 0 transformers in minimal net)
    # The current implementation adds lines and transformers separately, so let's check for "line_0", "line_1"
    line_traces = [trace for trace in fig.data if "line_" in trace.name]
    assert len(line_traces) == 2

    # Check for bus trace
    bus_trace = [trace for trace in fig.data if "bus_trace" == trace.name]
    assert len(bus_trace) == 1
    assert bus_trace[0].mode == "markers+text"
