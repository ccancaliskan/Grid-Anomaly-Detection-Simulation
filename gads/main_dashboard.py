import os
import time

import pandas as pd
import streamlit as st

from .simulation_state import SimulationState
from .simulation_core import run_simulation_step
from .plotting import create_interactive_network_plot
from .attack_manager import determine_attack_status
from .config import ATTACK_TYPES, ATTACK_DESCRIPTIONS, NUM_SIMULATION_STEPS


# ---------------------------------------------------------------------------
# Sidebar sections
# ---------------------------------------------------------------------------

def _draw_simulation_controls(state: SimulationState) -> None:
    st.sidebar.title("")
    col_start, col_reset = st.sidebar.columns(2)
    if col_start.button("Pause" if state.is_running else "Start", use_container_width=True):
        state.is_running = not state.is_running
        st.rerun()
    if col_reset.button("Reset", use_container_width=True):
        st.session_state.action = "reset"
        st.rerun()


def _draw_grid_selection(state: SimulationState) -> None:
    with st.sidebar.expander("Grid Selection", expanded=True):
        available = state.get_available_grids()
        if state.grid_type not in available:
            available.append(state.grid_type)

        st.selectbox(
            "Grid Type",
            options=available,
            key="grid_selector",
            index=available.index(state.grid_type),
        )

        with st.expander("Custom Grid from OSM"):
            root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            uploads_dir = os.path.join(root, "grid-importer", "uploads")
            os.makedirs(uploads_dir, exist_ok=True)

            uploaded = st.file_uploader("Upload .osm.pbf file", type="pbf")
            if uploaded is not None:
                file_path = os.path.join(uploads_dir, "custom.osm.pbf")
                with open(file_path, "wb") as fh:
                    fh.write(uploaded.getbuffer())

                if st.button("Process Uploaded File"):
                    with st.spinner("Processing… this may take a moment."):
                        ok, msg = state.run_importer(file_path, "custom_grid")
                        if ok:
                            st.success(msg)
                            time.sleep(0.5)
                            st.session_state.action = "process_custom_grid"
                            st.rerun()
                        else:
                            st.error(msg)

            if "Aachen (OSM)" in state.get_available_grids():
                if st.button("Delete Aachen Grid Data"):
                    state.delete_osm_grid("output")
                    st.session_state.action = "delete_osm_grid"
                    st.rerun()

            if "Custom (Uploaded)" in state.get_available_grids():
                if st.button("Delete Custom Grid Data"):
                    state.delete_osm_grid("custom_grid")
                    st.session_state.action = "delete_osm_grid"
                    st.rerun()


def _draw_bus_selection(state: SimulationState) -> None:
    with st.sidebar.expander("Bus Selection"):
        st.write("Select Bus to Monitor:")
        n_buses = len(state.net.bus)
        if n_buses > 0:
            max_bus = n_buses - 1
            st.slider("Bus", 0, max_bus, key="bus_slider", value=state.selected_bus)
            st.number_input(
                "Bus",
                0,
                max_bus,
                key="bus_num_input",
                value=state.selected_bus,
                label_visibility="collapsed",
            )


def _draw_attack_configuration(state: SimulationState) -> None:
    with st.sidebar.expander("Attack Configuration", expanded=True):
        selected_type = st.selectbox(
            "Attack Type",
            ATTACK_TYPES,
            key="attack_type_selector",
            index=ATTACK_TYPES.index(state.attack_type),
        )

        desc = ATTACK_DESCRIPTIONS.get(selected_type)
        if desc:
            st.info(desc)

        non_targeted = {"None", "Adaptive Campaign", "Custom Campaign", "Line Outage"}
        if selected_type not in non_targeted:
            st.slider("Number of Targets", 1, 10, key="num_attack_slider", value=state.num_attack_slider)

        if selected_type == "Adaptive Campaign":
            st.slider(
                "Campaign Intensity", 1, 10,
                key="adaptive_campaign_intensity",
                value=state.adaptive_campaign_intensity,
            )
        elif selected_type == "Liar Attack":
            st.slider("Liar Intensity", 1.0, 2.0, key="liar_intensity", value=state.liar_intensity)
        elif selected_type == "Overload Attack":
            st.slider("Overload Intensity", 1.0, 5.0, key="overload_intensity", value=state.overload_intensity)
        elif selected_type == "Flicker Attack":
            st.slider("Flicker Intensity", 1.0, 5.0, key="flicker_intensity", value=state.flicker_intensity)
        elif selected_type == "Stealth Attack":
            st.slider("Stealth Intensity", 0.85, 1.0, key="stealth_intensity", value=state.stealth_intensity, format="%.3f")
        elif selected_type == "Ramp Attack":
            st.slider("Ramp Rate", 0.01, 0.5, key="ramp_rate", value=state.ramp_rate)
        elif selected_type == "Custom Campaign":
            _draw_custom_campaign_builder(state)


def _draw_custom_campaign_builder(state: SimulationState) -> None:
    st.write("Build your own attack sequence:")

    with st.form("new_stage_form"):
        st.write("Add a new stage:")
        valid_types = [t for t in ATTACK_TYPES if t not in {"None", "Adaptive Campaign", "Custom Campaign"}]
        new_type = st.selectbox("Attack Type", valid_types)
        start_t, end_t = st.slider("Time Range", 0, NUM_SIMULATION_STEPS, (0, 10))
        intensity = st.slider("Intensity", 0.0, 5.0, 1.0)

        if new_type == "Line Outage":
            targets = st.multiselect("Target Lines", list(state.net.line.index))
        else:
            targets = st.multiselect(
                "Target Buses", [b for b in state.net.bus.index if b != 0]
            )

        if st.form_submit_button("Add Stage"):
            stage: dict = {
                "type": new_type,
                "range": range(start_t, end_t),
                "intensity": intensity,
                "buses": [] if new_type == "Line Outage" else targets,
                "lines": targets if new_type == "Line Outage" else [],
            }
            state.custom_campaign.append(stage)
            state.custom_campaign.sort(key=lambda s: s["range"].start)

    st.write("**Current Campaign:**")
    for i, stage in enumerate(state.custom_campaign):
        st.write(
            f"Stage {i + 1}: **{stage['type']}** "
            f"t={stage['range'].start}–{stage['range'].stop}"
        )

    if st.button("Clear Custom Campaign"):
        state.custom_campaign = []
        st.rerun()


def _draw_settings(state: SimulationState) -> None:
    with st.sidebar.expander("Settings"):
        st.slider("Sim Speed (s/step)", 0.01, 1.0, key="sim_speed", value=state.sim_speed)
        st.checkbox(
            "Halt on non-convergence",
            key="halt_on_non_convergence",
            value=state.halt_on_non_convergence,
        )
        if st.button("Export Ground Truth"):
            path = state.export_data_to_csv()
            st.success(f"Exported to {path}")


def draw_sidebar(state: SimulationState) -> None:
    """Render the full sidebar and handle interactions via st.session_state."""
    _draw_simulation_controls(state)
    _draw_grid_selection(state)
    _draw_bus_selection(state)
    _draw_attack_configuration(state)
    _draw_settings(state)


# ---------------------------------------------------------------------------
# Session-state initialisation & reconciliation
# ---------------------------------------------------------------------------

def handle_state_initialization_and_reconciliation() -> SimulationState:
    """
    Initialises SimulationState on first load and reconciles it with any
    grid-selection or reset actions that occurred in the previous rerun.
    """
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = SimulationState()

    if "grid_selector" not in st.session_state:
        st.session_state.grid_selector = st.session_state.sim_state.grid_type

    action = st.session_state.pop("action", None)
    if action == "process_custom_grid":
        st.session_state.grid_selector = "Custom (Uploaded)"
    elif action in {"delete_osm_grid", "reset"}:
        fallback = getattr(st.session_state.sim_state, "grid_type", "IEEE 33 Bus")
        st.session_state.grid_selector = fallback if action == "reset" else "IEEE 33 Bus"

    # Rebuild state when the grid type has changed
    current_grid = getattr(st.session_state.sim_state, "grid_type", None)
    if st.session_state.grid_selector != current_grid:
        st.session_state.sim_state = SimulationState(
            grid_type=st.session_state.grid_selector
        )
        for key in ("bus_slider", "bus_num_input"):
            st.session_state[key] = 0

    state: SimulationState = st.session_state.sim_state

    # Guard: selected bus must be in range for this grid
    if len(state.net.bus) > 0 and state.selected_bus >= len(state.net.bus):
        state.selected_bus = 0
        for key in ("bus_slider", "bus_num_input"):
            st.session_state[key] = 0

    return state


def _sync_state_from_widgets(state: SimulationState) -> None:
    """Pull widget values from session_state into the state object."""
    state.attack_type = st.session_state.get("attack_type_selector", state.attack_type)

    # Bus selection — slider and number_input are kept in sync with each other
    slider_val = st.session_state.get("bus_slider", state.selected_bus)
    num_val = st.session_state.get("bus_num_input", state.selected_bus)

    if slider_val != state.selected_bus:
        state.selected_bus = slider_val
        st.session_state["bus_num_input"] = slider_val
    elif num_val != state.selected_bus:
        state.selected_bus = num_val
        st.session_state["bus_slider"] = num_val

    state.num_attack_slider = st.session_state.get("num_attack_slider", state.num_attack_slider)
    state.sim_speed = st.session_state.get("sim_speed", state.sim_speed)
    state.halt_on_non_convergence = st.session_state.get(
        "halt_on_non_convergence", state.halt_on_non_convergence
    )
    state.adaptive_campaign_intensity = st.session_state.get(
        "adaptive_campaign_intensity", state.adaptive_campaign_intensity
    )
    state.liar_intensity = st.session_state.get("liar_intensity", state.liar_intensity)
    state.overload_intensity = st.session_state.get("overload_intensity", state.overload_intensity)
    state.flicker_intensity = st.session_state.get("flicker_intensity", state.flicker_intensity)
    state.stealth_intensity = st.session_state.get("stealth_intensity", state.stealth_intensity)
    state.ramp_rate = st.session_state.get("ramp_rate", state.ramp_rate)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_dashboard() -> None:
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")

    state = handle_state_initialization_and_reconciliation()
    _sync_state_from_widgets(state)

    # Regenerate adaptive campaign when intensity changes or campaign is empty
    if state.attack_type == "Adaptive Campaign":
        intensity_changed = (
            state.adaptive_campaign_intensity != state.generated_adaptive_campaign_intensity
        )
        if not state.generated_adaptive_campaign or intensity_changed:
            state.generate_and_store_campaign()

    draw_sidebar(state)

    if state.error_message:
        st.error(state.error_message)

    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)

    with st.expander("Attack Status", expanded=bool(is_attacked)):
        if is_attacked:
            st.write(f"**Attack Type:** {current_attack_type}")
            if attacked_buses:
                st.write(f"**Attacked Buses:** {', '.join(map(str, attacked_buses))}")
            if attacked_lines:
                st.write(f"**Attacked Lines:** {', '.join(map(str, attacked_lines))}")
        else:
            st.write("No active attack.")

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            create_interactive_network_plot(state.net, state.selected_bus),
            use_container_width=True,
        )
    with col2:
        st.markdown(f"Voltage at **Bus {state.selected_bus}**")
        if not state.data.empty:
            bus_data = state.data[state.data["bus_id"] == state.selected_bus]
            if not bus_data.empty:
                st.line_chart(bus_data.set_index("time_step")["vm_pu"])

    if state.is_running:
        run_simulation_step(state)
        if not state.is_running:
            st.success("Simulation finished or halted.")
        time.sleep(state.sim_speed)
        st.rerun()


if __name__ == "__main__":
    run_dashboard()
