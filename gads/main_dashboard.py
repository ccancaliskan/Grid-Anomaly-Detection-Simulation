import streamlit as st
import time
import pandas as pd

from gads.simulation_state import SimulationState
from gads.simulation_core import run_simulation_step
from gads.plotting import create_interactive_network_plot
from gads.attack_manager import determine_attack_status
from gads.config import ATTACK_TYPES, ATTACK_DESCRIPTIONS

# --- Callbacks ---
def on_grid_change():
    """When the grid type is changed, create a new SimulationState."""
    new_grid = st.session_state.grid_selector
    st.session_state.sim_state = SimulationState(grid_type=new_grid)

def on_attack_type_change():
    """When attack type is changed, update state and generate campaign if needed."""
    state = st.session_state.sim_state
    state.attack_type = st.session_state.attack_type_selector
    state.current_attack_targets = []
    if state.attack_type == "Adaptive Campaign":
        state.generate_and_store_campaign()

def on_bus_slider_change():
    st.session_state.sim_state.selected_bus = st.session_state.bus_slider
    st.session_state.bus_num_input = st.session_state.bus_slider

def on_bus_num_change():
    st.session_state.sim_state.selected_bus = st.session_state.bus_num_input
    st.session_state.bus_slider = st.session_state.bus_num_input

# --- UI Drawing Functions ---
def draw_sidebar(state: SimulationState):
    """Draws the entire sidebar UI."""
    st.sidebar.title("Grid Anomaly Detection Simulation")

    # --- Simulation Controls ---
    col_start, col_reset = st.sidebar.columns(2)
    button_icon = "⏸️" if state.is_running else "▶️"
    if col_start.button(button_icon, use_container_width=True):
        state.is_running = not state.is_running
    
    if col_reset.button("🔄", use_container_width=True):
        on_grid_change() # Re-create the state to reset

    # --- Grid and Bus Selection ---
    st.sidebar.selectbox(
        "Grid Type",
        options=list(state.GRID_MAPPING.keys()),
        key="grid_selector",
        on_change=on_grid_change,
        index=list(state.GRID_MAPPING.keys()).index(state.grid_type)
    )
    
    st.sidebar.write("Select Bus to Monitor:")
    bus_slider_col, bus_num_col = st.sidebar.columns([3, 1])
    bus_slider_col.slider(
        "Bus", 0, len(state.net.bus) - 1,
        key="bus_slider",
        on_change=on_bus_slider_change,
        label_visibility="collapsed"
    )
    bus_num_col.number_input(
        "Bus", 0, len(state.net.bus) - 1,
        key="bus_num_input",
        on_change=on_bus_num_change,
        label_visibility="collapsed"
    )

    # --- Attack Controls ---
    st.sidebar.header("Attack Configuration")
    st.sidebar.selectbox(
        "Attack Type", ATTACK_TYPES,
        key="attack_type_selector",
        on_change=on_attack_type_change,
        index=ATTACK_TYPES.index(state.attack_type)
    )
    description = ATTACK_DESCRIPTIONS.get(state.attack_type)
    if description:
        st.sidebar.info(description)

    # Sliders are updated via session_state and read by the core logic
    if state.attack_type not in ["None", "Adaptive Campaign", "Custom Campaign", "Line Outage"]:
        state.num_attack_slider = st.sidebar.slider("Number of Targets", 1, 10, state.num_attack_slider)

    if state.attack_type == "Liar Attack":
        state.liar_intensity = st.sidebar.slider("Liar Intensity", 0.8, 1.2, state.liar_intensity, 0.01)
    
    # ... more manual attack sliders could be added here

    # --- Other Settings ---
    st.sidebar.header("Settings")
    state.sim_speed = st.sidebar.slider("Sim Speed (s/step)", 0.01, 1.0, state.sim_speed, 0.01)
    state.halt_on_non_convergence = st.sidebar.checkbox("Halt on non-convergence", state.halt_on_non_convergence)
    
    if st.sidebar.button("Export Ground Truth"):
        file_path = state.export_data_to_csv()
        st.sidebar.success(f"Exported to {file_path}")


def run_dashboard():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")

    # --- State Management ---
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = SimulationState()

    state = st.session_state.sim_state

    # --- Draw UI ---
    draw_sidebar(state)

    # --- Main Content Area ---
    if state.error_message:
        st.error(state.error_message)

    _, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)
    attack_info_placeholder = st.empty()
    if state.is_running and current_attack_type != "None":
        if attacked_buses:
            attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on buses: {attacked_buses}</h3>", unsafe_allow_html=True)
        elif attacked_lines:
            attack_info_placeholder.markdown(f"<h3 style='text-align: center;'>{current_attack_type} Active on lines: {attacked_lines}</h3>", unsafe_allow_html=True)
    else:
        attack_info_placeholder.empty()
    
    col1, col2 = st.columns(2)
    with col1:
        network_plot_placeholder = st.empty()
    with col2:
        st.subheader(f"Voltage at Bus {state.selected_bus}")
        voltage_chart_placeholder = st.empty()

    # --- Simulation Loop ---
    while state.is_running:
        run_simulation_step(state)

        # Update UI components
        network_plot_placeholder.plotly_chart(create_interactive_network_plot(state.net, state.selected_bus), use_container_width=True)
        bus_data = state.data[state.data['bus_id'] == state.selected_bus]
        if not bus_data.empty:
            voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])
        
        # Check for stop conditions
        if not state.is_running:
            st.success("Simulation finished or halted.")
            attack_info_placeholder.empty()
            break
        
        time.sleep(state.sim_speed)
        st.rerun() # Rerun to reflect the single step change
    
    # Final UI update when paused or stopped
    network_plot_placeholder.plotly_chart(create_interactive_network_plot(state.net, state.selected_bus), use_container_width=True)
    bus_data = state.data[state.data['bus_id'] == state.selected_bus]
    if not bus_data.empty:
        voltage_chart_placeholder.line_chart(bus_data.set_index('time_step')['vm_pu'])


if __name__ == "__main__":
    run_dashboard()
