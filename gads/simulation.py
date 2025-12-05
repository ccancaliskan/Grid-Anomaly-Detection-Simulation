import numpy as np
import pandas as pd
import pandapower as pp 
from gads.config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR

def run_time_series_simulation(net, num_steps=NUM_SIMULATION_STEPS, noise_std_dev=NOISE_STD_DEV):
    """
    Runs a time series power flow simulation and saves the results.

    Args:
        net (pandapowerNet): The pandapower network.
        num_steps (int): The number of time steps to simulate.
        noise_std_dev (float): The standard deviation of the Gaussian noise to add.

    Returns:
        pd.DataFrame: A DataFrame containing the "Ground Truth" data.
    """
    # Store original load values
    original_loads = net.load.p_mw.copy()
    
    results_list = []
    
    for t in range(num_steps):
        # Simulate daily load profile with a sinusoidal pattern
        load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / num_steps)
        net.load.p_mw = original_loads * load_scaling
        
        # Run power flow
        pp.runpp(net)
        
        # Get results
        vm_pu = net.res_bus.vm_pu.copy()
        loading_percent = net.res_line.loading_percent.copy()
        
        # Add Gaussian noise
        vm_pu_noisy = vm_pu + np.random.normal(0, noise_std_dev, len(vm_pu))
        loading_percent_noisy = loading_percent + np.random.normal(0, noise_std_dev, len(loading_percent))
        
        # Store results for this time step
        step_results = {
            'time_step': t,
            'vm_pu': vm_pu_noisy,
            'loading_percent': loading_percent_noisy
        }
        results_list.append(step_results)

    # For simplicity, we will just save the bus data for now.
    # A more complete solution would handle bus and line data separately.
    bus_data = []
    for res in results_list:
        time_step = res['time_step']
        for i, vm in enumerate(res['vm_pu']):
            bus_data.append({'time_step': time_step, 'bus_id': i, 'vm_pu': vm})

    ground_truth_df = pd.DataFrame(bus_data)

    return ground_truth_df
