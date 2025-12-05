
import pandas as pd
import pandapower as pp
from gads.campaign_manager import generate_adaptive_campaign

def create_mock_net():
    """Creates a mock pandapower network for testing."""
    net = pp.create_empty_network()
    pp.create_bus(net, vn_kv=20.0, name="Bus 1")
    pp.create_bus(net, vn_kv=20.0, name="Bus 2")
    pp.create_bus(net, vn_kv=20.0, name="Bus 3")
    pp.create_line(net, from_bus=0, to_bus=1, length_km=1.0, std_type="N2XS(FL)2Y 1x300 RM/35 64/110 kV")
    return net

def test_generate_adaptive_campaign():
    """
    Tests the generate_adaptive_campaign function to ensure it generates a valid campaign.
    """
    net = create_mock_net()
    intensity = 5
    total_steps = 100
    campaign = generate_adaptive_campaign(intensity, net, total_steps)

    assert isinstance(campaign, list)
    if campaign:
        for stage in campaign:
            assert isinstance(stage, dict)
            assert "type" in stage
            assert "range" in stage
            assert "intensity" in stage
            if stage["type"] == "Line Outage":
                assert "lines" in stage
            else:
                assert "buses" in stage
