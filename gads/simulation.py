import pandapower as pp
import numpy as np

def create_ieee_33_bus_system():
    """
    Creates and returns the IEEE 33-bus system using pandapower.
    """
    net = pp.networks.case33bw()
    print("IEEE 33-bus system created successfully.")
    return net

def run_time_series_simulation(net, num_steps=96):
    """
    Runs a time series power flow simulation.

    Args:
        net (pandapowerNet): The pandapower network.
        num_steps (int): The number of time steps to simulate.

    Returns:
        list: A list of voltage magnitudes (vm_pu) for each time step.
    """
    # Store original load values
    original_loads = net.load.p_mw.copy()
    
    results = []
    
    for t in range(num_steps):
        # Simulate daily load profile with a sinusoidal pattern
        # This is a simple approximation of daily load changes
        load_scaling = 1.0 + 0.3 * np.sin(2 * np.pi * t / num_steps)
        net.load.p_mw = original_loads * load_scaling
        
        # Run power flow
        pp.runpp(net)
        
        # Store results (e.g., bus voltage magnitudes)
        results.append(net.res_bus.vm_pu.copy())
        
        print(f"Time step {t+1}/{num_steps} - Power flow calculated.")

    return results

if __name__ == "__main__":
    ieee_net = create_ieee_33_bus_system()
    time_series_results = run_time_series_simulation(ieee_net)
    
    print(f"\nSimulation finished. Collected {len(time_series_results)} time steps of data.")
    print("Example data from the first time step:")
    print(time_series_results[0])
