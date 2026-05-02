"""
Standalone (non-Streamlit) time-series simulation helper.

Used for offline ground-truth generation and batch experiments.
"""

import numpy as np
import pandas as pd
import pandapower as pp

from .config import NUM_SIMULATION_STEPS, NOISE_STD_DEV, LOAD_SCALE_FACTOR


def run_time_series_simulation(
    net,
    num_steps: int = NUM_SIMULATION_STEPS,
    noise_std_dev: float = NOISE_STD_DEV,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run a sinusoidal load-profile simulation and return noisy measurements.

    Args:
        net:            A pandapowerNet object (modified in place, then restored).
        num_steps:      Number of time steps to simulate.
        noise_std_dev:  Standard deviation of Gaussian sensor noise.

    Returns:
        bus_df:  DataFrame with columns [time_step, bus_id, vm_pu].
        line_df: DataFrame with columns [time_step, line_id, loading_percent].

    Notes:
        - Original loads are restored after the simulation.
        - BUG FIX (original): bus_id was set via enumerate() position, not the
          actual pandapower bus index.  Non-contiguous indices (e.g. after OSM
          grid construction) would have produced wrong bus_id values.
        - BUG FIX (original): line data was computed every step but discarded;
          now returned as a second DataFrame.
    """
    original_loads = net.load.p_mw.copy()
    bus_rows: list[dict] = []
    line_rows: list[dict] = []

    try:
        for t in range(num_steps):
            load_scaling = 1.0 + LOAD_SCALE_FACTOR * np.sin(2 * np.pi * t / num_steps)
            net.load.p_mw = original_loads * load_scaling

            pp.runpp(net)

            vm_pu: pd.Series = net.res_bus.vm_pu + np.random.normal(
                0, noise_std_dev, len(net.res_bus)
            )
            loading: pd.Series = net.res_line.loading_percent + np.random.normal(
                0, noise_std_dev, len(net.res_line)
            )

            # Use actual bus/line index values, not positional integers
            for bus_id, vm in vm_pu.items():
                bus_rows.append({"time_step": t, "bus_id": bus_id, "vm_pu": vm})

            for line_id, pct in loading.items():
                line_rows.append({"time_step": t, "line_id": line_id, "loading_percent": pct})

    finally:
        # Always restore original loads even if an exception occurs mid-run
        net.load.p_mw = original_loads

    bus_df = pd.DataFrame(bus_rows)
    line_df = pd.DataFrame(line_rows)
    return bus_df, line_df
