import streamlit as st
import time
import pandas as pd
import os

from gads.simulation_state import SimulationState
from gads.simulation_core import run_simulation_step
from gads.plotting import create_interactive_network_plot
from gads.attack_manager import determine_attack_status
from gads.config import ATTACK_TYPES, ATTACK_DESCRIPTIONS


def draw_sidebar(state: SimulationState):
    """Draws the entire sidebar UI and handles user interaction via st.session_state."""
    st.sidebar.title("Grid Anomaly Detection Simulation")

    # --- Simulation Controls ---
    col_start, col_reset = st.sidebar.columns(2)
    if col_start.button("▶️ Start" if not state.is_running else "⏸️ Pause", use_container_width=True):
        state.is_running = not state.is_running
        st.rerun()

    if col_reset.button("🔄 Reset", use_container_width=True):
        st.session_state.action = "reset"
        st.rerun()

    # --- Grid Selection ---
    available_grids = state.get_available_grids()
    # Ensure the current state's grid type is always in the options
    if state.grid_type not in available_grids:
        available_grids.append(state.grid_type)

    st.sidebar.selectbox(
        "Grid Type",
        options=available_grids,
        key="grid_selector",
        index=available_grids.index(state.grid_type)
    )
    
    # --- Custom Grid Uploader ---
    st.sidebar.header("Custom Grid from OSM")
    
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    uploads_dir = os.path.join(project_root, "grid-importer", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    uploaded_file = st.sidebar.file_uploader("Upload .osm.pbf file", type="pbf")
    
    if uploaded_file is not None:
        file_path = os.path.join(uploads_dir, "custom.osm.pbf")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        if st.sidebar.button("Process Uploaded File"):
            with st.spinner("Processing... This may take a moment."):
                success, message = state.run_importer(file_path, "custom_grid")
                if success:
                    st.sidebar.success(message)
                    time.sleep(0.5) # Give filesystem a moment to sync
                    st.session_state.action = "process_custom_grid"
                    st.rerun()
                else:
                    st.sidebar.error(message)

    # --- Delete Buttons for OSM Grids ---
    if "Aachen (OSM)" in state.get_available_grids():
        if st.sidebar.button("Delete Aachen Grid Data"):
            state.delete_osm_grid("output")
            st.session_state.action = "delete_osm_grid"
            st.rerun()

    if "Custom (Uploaded)" in state.get_available_grids():
        if st.sidebar.button("Delete Custom Grid Data"):
            state.delete_osm_grid("custom_grid")
            st.session_state.action = "delete_osm_grid"
            st.rerun()
            
    # --- Bus Selection ---
    st.sidebar.write("Select Bus to Monitor:")
    if len(state.net.bus) > 0:
        st.sidebar.slider("Bus", 0, len(state.net.bus) - 1, key="bus_slider", value=state.selected_bus)
        st.sidebar.number_input("Bus", 0, len(state.net.bus) - 1, key="bus_num_input", value=state.selected_bus, label_visibility="collapsed")
    
    # --- Attack Controls ---
    st.sidebar.header("Attack Configuration")
    st.sidebar.selectbox("Attack Type", ATTACK_TYPES, key="attack_type_selector", index=ATTACK_TYPES.index(state.attack_type))
    description = ATTACK_DESCRIPTIONS.get(st.session_state.attack_type_selector)
    if description: st.sidebar.info(description)

    if st.session_state.attack_type_selector not in ["None", "Adaptive Campaign", "Custom Campaign", "Line Outage"]:
        st.sidebar.slider("Number of Targets", 1, 10, key="num_attack_slider", value=state.num_attack_slider)
    
    # --- Settings ---
    st.sidebar.header("Settings")
    st.sidebar.slider("Sim Speed (s/step)", 0.01, 1.0, key="sim_speed", value=state.sim_speed)
    st.sidebar.checkbox("Halt on non-convergence", key="halt_on_non_convergence", value=state.halt_on_non_convergence)
    
    if st.sidebar.button("Export Ground Truth"):
        file_path = state.export_data_to_csv()
        st.sidebar.success(f"Exported to {file_path}")

def run_dashboard():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")

    # --- State Initialization & Reconciliation ---
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = SimulationState()
    
    if "grid_selector" not in st.session_state:
        st.session_state.grid_selector = st.session_state.sim_state.grid_type

    # Handle actions from buttons first
    action = st.session_state.pop("action", None)
    if action == "process_custom_grid":
        st.session_state.grid_selector = "Custom (Uploaded)"
    elif action in ["delete_osm_grid", "reset"]:
        sim_state_grid_type = getattr(st.session_state.get("sim_state"), "grid_type", "IEEE 33 Bus")
        st.session_state.grid_selector = sim_state_grid_type if action == "reset" else "IEEE 33 Bus"

    # If the user's grid selection has changed, create a new state
    sim_state_grid_type = getattr(st.session_state.get("sim_state"), "grid_type", None)
    if st.session_state.grid_selector != sim_state_grid_type:
        st.session_state.sim_state = SimulationState(grid_type=st.session_state.grid_selector)
        
    state = st.session_state.sim_state

    # Ensure selected_bus is valid for the current grid
    if state.selected_bus >= len(state.net.bus):
        state.selected_bus = 0
        st.session_state.bus_slider = 0
        st.session_state.bus_num_input = 0

    # Sync widget states from the main state object
    state.attack_type = st.session_state.get("attack_type_selector", state.attack_type)
    state.selected_bus = st.session_state.get("bus_slider", state.selected_bus)
    state.num_attack_slider = st.session_state.get("num_attack_slider", state.num_attack_slider)
    state.sim_speed = st.session_state.get("sim_speed", state.sim_speed)
    state.halt_on_non_convergence = st.session_state.get("halt_on_non_convergence", state.halt_on_non_convergence)

    # --- UI and Simulation ---
    draw_sidebar(state)

    if state.error_message: st.error(state.error_message)

    _, current_attack_type, _, _ = determine_attack_status(state)
    
    # Main content area drawing logic here...
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_interactive_network_plot(state.net, state.selected_bus), use_container_width=True)
    with col2:
        st.subheader(f"Voltage at Bus {state.selected_bus}")
        if not state.data.empty:
            bus_data = state.data[state.data['bus_id'] == state.selected_bus]
            if not bus_data.empty:
                st.line_chart(bus_data.set_index('time_step')['vm_pu'])

    if state.is_running:
        run_simulation_step(state)
        if not state.is_running:
            st.success("Simulation finished or halted.")
        time.sleep(state.sim_speed)
        st.rerun()

if __name__ == "__main__":
    run_dashboard()
