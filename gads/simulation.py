import pandapower as pp
import numpy as np
import pandas as pd
import plotly.graph_objects as go

def create_ieee_33_bus_system():
    """
    Creates and returns the IEEE 33-bus system using pandapower.
    """
    net = pp.networks.case33bw()
    
    # Manually create bus geodata
    num_buses = len(net.bus)
    coords = []
    for i in range(num_buses):
        coords.append((i % 6, i // 6))
    
    bus_geodata = pd.DataFrame(coords, columns=['x', 'y'], index=net.bus.index)
    net.bus_geodata = bus_geodata
    
    return net

def create_interactive_network_plot(net, selected_bus=None):
    """
    Generates a more customizable interactive plot of the network.

    Args:
        net (pandapowerNet): The pandapower network.
        selected_bus (int, optional): The ID of the bus to highlight. Defaults to None.

    Returns:
        go.Figure: A plotly graph object figure.
    """
    # Get bus coordinates
    bus_coords = net.bus_geodata[['x', 'y']]
    
    # Line traces
    line_traces = []
    for i, line in net.line.iterrows():
        from_bus = net.bus_geodata.loc[line.from_bus]
        to_bus = net.bus_geodata.loc[line.to_bus]
        line_traces.append(go.Scatter(
            x=[from_bus.x, to_bus.x],
            y=[from_bus.y, to_bus.y],
            mode='lines',
            line=dict(width=2, color='grey'),
            hoverinfo='none',
            name=f'line_{i}'
        ))

    # Bus trace
    bus_trace = go.Scatter(
        x=bus_coords.x,
        y=bus_coords.y,
        mode='markers+text', # Display bus names on nodes
        marker=dict(
            size=10,
            color='#3366CC',
        ),
        text=[f"{i}" for i in net.bus.index], # Display bus ID on node
        textposition="top center",
        hovertext=[f"Bus {i}<br>Voltage: {net.res_bus.vm_pu.at[i]:.3f}" if not net.res_bus.empty and not pd.isna(net.res_bus.vm_pu.at[i]) else f"Bus {i}" for i in net.bus.index], # Voltage info on hover with bus name
        hoverinfo='text',
        name='bus_trace'
    )
    
    # Highlight trace
    highlight_trace = None
    if selected_bus is not None and selected_bus in net.bus_geodata.index:
        highlight_coords = net.bus_geodata.loc[selected_bus]
        highlight_trace = go.Scatter(
            x=[highlight_coords.x],
            y=[highlight_coords.y],
            mode='markers',
            marker=dict(
                size=15, # Slightly larger than regular bus markers
                color='green',
                symbol='circle' # Use default circle symbol
            ),
            hoverinfo='none',
            name='highlight_trace'
        )

    data = line_traces + [bus_trace]
    if highlight_trace:
        data.append(highlight_trace)

    layout = go.Layout(
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=0, r=0, t=0, b=0)
    )

    fig = go.Figure(data=data, layout=layout)
    return fig


def run_time_series_simulation(net, num_steps=96, noise_std_dev=0.005):
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
        load_scaling = 1.0 + 0.3 * np.sin(2 * np.pi * t / num_steps)
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

    ground_.truth_df = pd.DataFrame(bus_data)

    return ground_truth_df
