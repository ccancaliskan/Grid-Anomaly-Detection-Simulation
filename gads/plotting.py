import pandas as pd
import plotly.graph_objects as go


def _create_line_trace(
    net, from_bus_idx: int, to_bus_idx: int, color: str, width: int, name: str
) -> go.Scatter:
    """Return a Plotly Scatter trace for a single grid edge."""
    from_bus = net.bus_geodata.loc[from_bus_idx]
    to_bus = net.bus_geodata.loc[to_bus_idx]
    return go.Scatter(
        x=[from_bus.x, to_bus.x],
        y=[from_bus.y, to_bus.y],
        mode="lines",
        line=dict(width=width, color=color),
        hoverinfo="none",
        name=name,
    )


def _bus_hover_text(net, bus_id: int) -> str:
    """Build the hover label for a bus, safely handling missing or NaN results."""
    if net.res_bus.empty:
        return f"Bus {bus_id}"
    # BUG FIX: .at[] raises KeyError when the index is non-contiguous (e.g. OSM grids).
    # Use .get() via loc-based lookup with a default instead.
    try:
        vm = net.res_bus.vm_pu.loc[bus_id]
        if pd.isna(vm):
            return f"Bus {bus_id}"
        return f"Bus {bus_id}<br>Voltage: {vm:.3f} pu"
    except KeyError:
        return f"Bus {bus_id}"


def create_interactive_network_plot(net, selected_bus: int | None = None) -> go.Figure:
    """
    Build an interactive Plotly figure of the pandapower network.

    Args:
        net: pandapowerNet object (must have bus_geodata populated).
        selected_bus: Bus ID to highlight in green.

    Returns:
        A ``go.Figure`` ready for ``st.plotly_chart``.
    """
    bus_geodata = net.bus_geodata[["x", "y"]]

    # --- Edge traces ---
    traces: list[go.BaseTraceType] = []

    for i, line in net.line.iterrows():
        # Skip lines whose endpoints lack geodata (defensive for OSM grids)
        if line.from_bus not in bus_geodata.index or line.to_bus not in bus_geodata.index:
            continue
        traces.append(_create_line_trace(net, line.from_bus, line.to_bus, "grey", 2, f"line_{i}"))

    for i, trafo in net.trafo.iterrows():
        if trafo.hv_bus not in bus_geodata.index or trafo.lv_bus not in bus_geodata.index:
            continue
        traces.append(_create_line_trace(net, trafo.hv_bus, trafo.lv_bus, "orange", 2, f"trafo_{i}"))

    # --- Bus trace ---
    bus_ids = list(net.bus.index)
    traces.append(
        go.Scatter(
            x=bus_geodata.x.tolist(),
            y=bus_geodata.y.tolist(),
            mode="markers+text",
            marker=dict(size=10, color="#3366CC"),
            text=[str(i) for i in bus_ids],
            textposition="top center",
            hovertext=[_bus_hover_text(net, i) for i in bus_ids],
            hoverinfo="text",
            name="buses",
        )
    )

    # --- Highlight selected bus ---
    if selected_bus is not None and selected_bus in bus_geodata.index:
        hl = bus_geodata.loc[selected_bus]
        traces.append(
            go.Scatter(
                x=[hl.x],
                y=[hl.y],
                mode="markers",
                marker=dict(size=15, color="green", symbol="circle"),
                hoverinfo="none",
                name="selected",
            )
        )

    layout = go.Layout(
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        margin=dict(l=0, r=0, t=0, b=0),
    )

    return go.Figure(data=traces, layout=layout)
