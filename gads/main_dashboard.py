import streamlit as st
import time
import pandas as pd
import os

from gads.simulation_state import SimulationState
from gads.simulation_core import run_simulation_step
from gads.plotting import create_interactive_network_plot
from gads.attack_manager import determine_attack_status
from gads.config import ATTACK_TYPES, ATTACK_DESCRIPTIONS, NUM_SIMULATION_STEPS


def _draw_simulation_controls(state: SimulationState):
    st.sidebar.title("")
    col_start, col_reset = st.sidebar.columns(2)
    if col_start.button("Start" if not state.is_running else "⏸️ Pause", use_container_width=True):
        state.is_running = not state.is_running
        st.rerun()

    if col_reset.button("Reset", use_container_width=True):
        st.session_state.action = "reset"
        st.rerun()

def _draw_grid_selection(state: SimulationState):
    with st.sidebar.expander("Grid Selection", expanded=True):
        available_grids = state.get_available_grids()
        if state.grid_type not in available_grids:
            available_grids.append(state.grid_type)

        st.selectbox(
            "Grid Type",
            options=available_grids,
            key="grid_selector",
            index=available_grids.index(state.grid_type)
        )
        
        with st.expander("Custom Grid from OSM"):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            uploads_dir = os.path.join(project_root, "grid-importer", "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            
            uploaded_file = st.file_uploader("Upload .osm.pbf file", type="pbf")
            
            if uploaded_file is not None:
                file_path = os.path.join(uploads_dir, "custom.osm.pbf")
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                if st.button("Process Uploaded File"):
                    with st.spinner("Processing... This may take a moment."):
                        success, message = state.run_importer(file_path, "custom_grid")
                        if success:
                            st.success(message)
                            time.sleep(0.5)
                            st.session_state.action = "process_custom_grid"
                            st.rerun()
                        else:
                            st.error(message)

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

def _draw_bus_selection(state: SimulationState):
    with st.sidebar.expander("Bus Selection"):
        st.write("Select Bus to Monitor:")
        if len(state.net.bus) > 0:
            st.slider("Bus", 0, len(state.net.bus) - 1, key="bus_slider", value=state.selected_bus)
            st.number_input("Bus", 0, len(state.net.bus) - 1, key="bus_num_input", value=state.selected_bus, label_visibility="collapsed")

def _draw_attack_configuration(state: SimulationState):
    with st.sidebar.expander("Attack Configuration", expanded=True):
        st.selectbox("Attack Type", ATTACK_TYPES, key="attack_type_selector", index=ATTACK_TYPES.index(state.attack_type))
        description = ATTACK_DESCRIPTIONS.get(st.session_state.attack_type_selector)
        if description: st.info(description)

        if st.session_state.attack_type_selector == "Adaptive Campaign":
            st.slider("Campaign Intensity", 1, 10, key="adaptive_campaign_intensity", value=state.adaptive_campaign_intensity)

        if st.session_state.attack_type_selector not in ["None", "Adaptive Campaign", "Custom Campaign", "Line Outage"]:
            st.slider("Number of Targets", 1, 10, key="num_attack_slider", value=state.num_attack_slider)
        
        if st.session_state.attack_type_selector == "Liar Attack":
            st.slider("Liar Intensity", 1.0, 2.0, key="liar_intensity", value=state.liar_intensity)
        elif st.session_state.attack_type_selector == "Overload Attack":
            st.slider("Overload Intensity", 1.0, 5.0, key="overload_intensity", value=state.overload_intensity)
        elif st.session_state.attack_type_selector == "Flicker Attack":
            st.slider("Flicker Intensity", 1.0, 5.0, key="flicker_intensity", value=state.flicker_intensity)
        elif st.session_state.attack_type_selector == "Stealth Attack":
            st.slider("Stealth Intensity", 1.0, 1.1, key="stealth_intensity", value=state.stealth_intensity, format="%.3f")
        elif st.session_state.attack_type_selector == "Ramp Attack":
            st.slider("Ramp Rate", 0.01, 0.5, key="ramp_rate", value=state.ramp_rate)

        elif st.session_state.attack_type_selector == "Custom Campaign":
            st.write("Build your own attack sequence:")
            
            with st.form("new_stage_form"):
                st.write("Add a new stage:")
                new_stage_type = st.selectbox("Attack Type", [t for t in ATTACK_TYPES if t not in ["None", "Adaptive Campaign", "Custom Campaign"]])
                
                start_time, end_time = st.slider("Time Range", 0, NUM_SIMULATION_STEPS, (0, 10))
                
                intensity = st.slider("Intensity", 0.0, 5.0, 1.0)
                
                if new_stage_type == "Line Outage":
                    targets = st.multiselect("Target Lines", list(state.net.line.index))
                else:
                    targets = st.multiselect("Target Buses", [b for b in state.net.bus.index if b != 0])
                
                submitted = st.form_submit_button("Add Stage")
                if submitted:
                    new_stage = {
                        "type": new_stage_type,
                        "range": range(start_time, end_time),
                        "intensity": intensity,
                    }
                    if new_stage_type == "Line Outage":
                        new_stage["lines"] = targets
                    else:
                        new_stage["buses"] = targets
                    
                    state.custom_campaign.append(new_stage)
                    state.custom_campaign.sort(key=lambda s: s["range"].start)

            st.write("Current Campaign:")
            for i, stage in enumerate(state.custom_campaign):
                st.write(f"Stage {i+1}: {stage['type']} from {stage['range'].start} to {stage['range'].stop}")

            if st.button("Clear Custom Campaign"):
                state.custom_campaign = []
                st.rerun()

def _draw_settings(state: SimulationState):
    with st.sidebar.expander("Settings"):
        st.slider("Sim Speed (s/step)", 0.01, 1.0, key="sim_speed", value=state.sim_speed)
        st.checkbox("Halt on non-convergence", key="halt_on_non_convergence", value=state.halt_on_non_convergence)
        
        if st.button("Export Ground Truth"):
            file_path = state.export_data_to_csv()
            st.success(f"Exported to {file_path}")

def draw_sidebar(state: SimulationState):
    """Draws the entire sidebar UI and handles user interaction via st.session_state."""
    _draw_simulation_controls(state)
    _draw_grid_selection(state)
    _draw_bus_selection(state)
    _draw_attack_configuration(state)
    _draw_settings(state)

def handle_state_initialization_and_reconciliation():
    """Handles all session state initialization and reconciliation."""
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = SimulationState()
    
    if "grid_selector" not in st.session_state:
        st.session_state.grid_selector = st.session_state.sim_state.grid_type

    action = st.session_state.pop("action", None)
    if action == "process_custom_grid":
        st.session_state.grid_selector = "Custom (Uploaded)"
    elif action in ["delete_osm_grid", "reset"]:
        sim_state_grid_type = getattr(st.session_state.get("sim_state"), "grid_type", "IEEE 33 Bus")
        st.session_state.grid_selector = sim_state_grid_type if action == "reset" else "IEEE 33 Bus"

    sim_state_grid_type = getattr(st.session_state.get("sim_state"), "grid_type", None)
    if st.session_state.grid_selector != sim_state_grid_type:
        st.session_state.sim_state = SimulationState(grid_type=st.session_state.grid_selector)
        st.session_state.sim_state.selected_bus = 0
        st.session_state.bus_slider = 0
        st.session_state.bus_num_input = 0
    
    state = st.session_state.sim_state
    
    if len(state.net.bus) > 0 and state.selected_bus >= len(state.net.bus):
        state.selected_bus = 0
        st.session_state.bus_slider = 0
        st.session_state.bus_num_input = 0
        
    return state

def run_dashboard():
    """Main function to run the Streamlit dashboard."""
    st.set_page_config(layout="wide")

    state = handle_state_initialization_and_reconciliation()

    # Sync widget states from the main state object
    state.attack_type = st.session_state.get("attack_type_selector", state.attack_type)
    
    if 'bus_slider' in st.session_state and st.session_state.bus_slider != state.selected_bus:
        state.selected_bus = st.session_state.bus_slider
        st.session_state.bus_num_input = state.selected_bus
    elif 'bus_num_input' in st.session_state and st.session_state.bus_num_input != state.selected_bus:
        state.selected_bus = st.session_state.bus_num_input
        st.session_state.bus_slider = state.selected_bus

    state.num_attack_slider = st.session_state.get("num_attack_slider", state.num_attack_slider)
    state.sim_speed = st.session_state.get("sim_speed", state.sim_speed)
    state.halt_on_non_convergence = st.session_state.get("halt_on_non_convergence", state.halt_on_non_convergence)
    state.adaptive_campaign_intensity = st.session_state.get("adaptive_campaign_intensity", state.adaptive_campaign_intensity)
    state.liar_intensity = st.session_state.get("liar_intensity", state.liar_intensity)
    state.overload_intensity = st.session_state.get("overload_intensity", state.overload_intensity)
    state.flicker_intensity = st.session_state.get("flicker_intensity", state.flicker_intensity)
    state.stealth_intensity = st.session_state.get("stealth_intensity", state.stealth_intensity)
    state.ramp_rate = st.session_state.get("ramp_rate", state.ramp_rate)

    if state.attack_type == "Adaptive Campaign":
        if not state.generated_adaptive_campaign or state.adaptive_campaign_intensity != getattr(state, 'generated_adaptive_campaign_intensity', None):
            state.generate_and_store_campaign()
            state.generated_adaptive_campaign_intensity = state.adaptive_campaign_intensity

    # --- UI and Simulation ---
    draw_sidebar(state)

    if state.error_message: st.error(state.error_message)

    is_attacked, current_attack_type, attacked_buses, attacked_lines = determine_attack_status(state)

    with st.expander("Attack Status", expanded=is_attacked):
        if is_attacked:
            st.write(f"**Attack Type:** {current_attack_type}")
            if attacked_buses:
                st.write(f"**Attacked Buses:** {', '.join(map(str, attacked_buses))}")
            if attacked_lines:
                st.write(f"**Attacked Lines:** {', '.join(map(str, attacked_lines))}")
        else:
            st.write("No active attack.")
    
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
