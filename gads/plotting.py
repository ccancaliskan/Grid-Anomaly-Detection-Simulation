import pandas as pd
import plotly.graph_objects as go

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
    # Add lines
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
    
    # Add transformers
    for i, trafo in net.trafo.iterrows():
        from_bus = net.bus_geodata.loc[trafo.hv_bus]
        to_bus = net.bus_geodata.loc[trafo.lv_bus]
        line_traces.append(go.Scatter(
            x=[from_bus.x, to_bus.x],
            y=[from_bus.y, to_bus.y],
            mode='lines',
            line=dict(width=2, color='orange'), # Use a different color for transformers
            hoverinfo='none',
            name=f'trafo_{i}'
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
