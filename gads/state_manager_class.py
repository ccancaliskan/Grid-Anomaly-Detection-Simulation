import math
import streamlit as st
import pandas as pd
import pandapower as pp
import numpy as np # Import numpy for net.bus index
import random
from gads.campaign_manager import generate_adaptive_campaign
from gads.config import NUM_SIMULATION_STEPS
import networkx as nx

class StateManager:

    GRID_MAPPING = {
        "IEEE 33 Bus": pp.networks.case33bw,
        "IEEE 14 Bus": pp.networks.case14,
        "IEEE 30 Bus": pp.networks.case30,
        "IEEE 118 Bus": pp.networks.case118,
    }

    def __init__(self):
        pass

    def initialize_session_state(self, force=False, grid_type="IEEE 33 Bus"):
        """Initializes all session state variables if they don't exist or if forced."""
        if not force and "initialized" in st.session_state:
            return

        st.session_state.initialized = True
        st.session_state.is_running = False
        st.session_state.time_step = 0
        st.session_state.grid_type = grid_type
        st.session_state.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu', 'is_attacked'])
        
        # Load the selected grid
        net = self.GRID_MAPPING[grid_type]()

        # Generate geo-data if it doesn't exist
        if 'bus_geodata' not in net or net.bus_geodata.empty:
            mg = pp.topology.create_nxgraph(net) # Create a networkx graph
            # Check if graph is empty or has disconnected components, spring_layout might struggle
            if mg.number_of_nodes() == 0:
                # Fallback to simple grid if no nodes
                num_buses = len(net.bus)
                side_length = math.ceil(math.sqrt(num_buses))
                coords_dict = {i: (i % side_length, i // side_length) for i in net.bus.index}
            else:
                # Use spring layout for better visualization of topology
                coords_dict = nx.spring_layout(mg, dim=2, seed=42) # Use a seed for reproducibility

            coords_df = pd.DataFrame.from_dict(coords_dict, orient='index', columns=['x', 'y'])
            # Ensure index matches bus indices
            net.bus_geodata = coords_df.loc[net.bus.index]


        st.session_state.net = net
        st.session_state.original_loads = net.load.p_mw.copy()
        try:
            if net.res_bus.empty:
                pp.runpp(net)
        except Exception as e:
            # Some grids might not converge with default settings
            st.warning(f"Initial power flow for {grid_type} failed: {e}")


        # UI and Attack State
        st.session_state.attack_type = "None"
        st.session_state.liar_intensity = 1.1
        st.session_state.overload_intensity = 3.0
        st.session_state.flicker_intensity = 2.0
        st.session_state.stealth_intensity = 1.01
        st.session_state.ramp_rate = 0.1
        st.session_state.ramp_level = 1.0
        st.session_state.custom_campaign = []
        st.session_state.error_message = ""
        st.session_state.selected_bus = 0
        st.session_state.bus_slider = 0
        st.session_state.bus_num_input = 0
        st.session_state.sim_speed = 0.1
        st.session_state.num_attacked_buses = 1
        st.session_state.current_attack_targets = []
        st.session_state.num_attack_slider = 1
        st.session_state.is_converged = True
        st.session_state.halt_on_non_convergence = False
        st.session_state.data_replay_buffer = None
        st.session_state.line_outage_target = None
        st.session_state.voltage_history = []
        st.session_state.adaptive_campaign_intensity = 1
        st.session_state.generated_adaptive_campaign = []

    def on_attack_type_change(self):
        """Callback to update the main attack_type state from the widget's state and handle side-effects."""
        st.session_state.attack_type = st.session_state.attack_type_selector
        if st.session_state.attack_type == "Adaptive Campaign":
            self.generate_and_store_campaign()
        if st.session_state.attack_type != "Ramp Attack":
            st.session_state.ramp_level = 1.0
        st.session_state.current_attack_targets = []

    def generate_and_store_campaign(self):
        intensity = self.get_adaptive_campaign_intensity()
        net = self.get_net()
        campaign = generate_adaptive_campaign(intensity, net, NUM_SIMULATION_STEPS)
        self.set_generated_adaptive_campaign(campaign)

    def sync_bus_from_slider(self):
        """Callback to synchronize bus selection from slider to number input."""
        st.session_state.selected_bus = st.session_state.bus_slider
        st.session_state.bus_num_input = st.session_state.bus_slider

    def sync_bus_from_num_input(self):
        """Callback to synchronize bus selection from number input to slider."""
        st.session_state.selected_bus = st.session_state.bus_num_input
        st.session_state.bus_slider = st.session_state.bus_num_input

    def on_intensity_change(self):
        st.session_state.adaptive_campaign_intensity = st.session_state.adaptive_campaign_intensity_slider
        self.generate_and_store_campaign()

    def toggle_running(self):
        """Callback to toggle the simulation running state."""
        st.session_state.is_running = not st.session_state.is_running

    def export_data_to_csv(self):
        """Exports the collected simulation data to a CSV file."""
        data = self.get_data()
        if data.empty:
            st.toast("No data to export.", icon="⚠️")
            return
            
        file_path = "simulation_ground_truth.csv"
        try:
            data.to_csv(file_path, index=False)
            st.toast(f"Data exported to {file_path}", icon="✅")
        except Exception as e:
            st.toast(f"Error exporting data: {e}", icon="❌")

    # --- Getter methods for state variables ---
    def get_grid_type(self):
        return st.session_state.grid_type

    def get_is_running(self):
        return st.session_state.is_running

    def get_time_step(self):
        return st.session_state.time_step

    def get_data(self):
        return st.session_state.data

    def get_net(self):
        return st.session_state.net

    def get_original_loads(self):
        return st.session_state.original_loads

    def get_attack_type(self):
        return st.session_state.attack_type

    def get_liar_intensity(self):
        return st.session_state.liar_intensity

    def get_overload_intensity(self):
        return st.session_state.overload_intensity

    def get_flicker_intensity(self):
        return st.session_state.flicker_intensity

    def get_stealth_intensity(self):
        return st.session_state.stealth_intensity

    def get_ramp_rate(self):
        return st.session_state.ramp_rate

    def get_ramp_level(self):
        return st.session_state.ramp_level

    def get_custom_campaign(self):
        return st.session_state.custom_campaign

    def get_error_message(self):
        return st.session_state.error_message

    def get_selected_bus(self):
        return st.session_state.selected_bus

    def get_bus_slider(self):
        return st.session_state.bus_slider

    def get_bus_num_input(self):
        return st.session_state.bus_num_input

    def get_sim_speed(self):
        return st.session_state.sim_speed

    def get_num_attacked_buses(self):
        return st.session_state.num_attacked_buses

    def get_current_attack_targets(self):
        return st.session_state.current_attack_targets

    def get_num_attack_slider(self):
        return st.session_state.num_attack_slider

    def get_is_converged(self):
        return st.session_state.is_converged

    def get_halt_on_non_convergence(self):
        return st.session_state.halt_on_non_convergence

    def get_data_replay_buffer(self):
        return st.session_state.data_replay_buffer

    def get_line_outage_target(self):
        return st.session_state.line_outage_target

    def get_voltage_history(self):
        return st.session_state.voltage_history

    def get_adaptive_campaign_intensity(self):
        return st.session_state.adaptive_campaign_intensity

    def get_generated_adaptive_campaign(self):
        return st.session_state.generated_adaptive_campaign

    # --- Setter methods for state variables ---
    def set_grid_type(self, value):
        st.session_state.grid_type = value

    def set_is_running(self, value):
        st.session_state.is_running = value

    def set_time_step(self, value):
        st.session_state.time_step = value

    def set_data(self, value):
        st.session_state.data = value

    def set_net(self, value):
        st.session_state.net = value

    def set_original_loads(self, value):
        st.session_state.original_loads = value

    def set_attack_type(self, value):
        st.session_state.attack_type = value

    def set_liar_intensity(self, value):
        st.session_state.liar_intensity = value

    def set_overload_intensity(self, value):
        st.session_state.overload_intensity = value

    def set_flicker_intensity(self, value):
        st.session_state.flicker_intensity = value

    def set_stealth_intensity(self, value):
        st.session_state.stealth_intensity = value

    def set_ramp_rate(self, value):
        st.session_state.ramp_rate = value

    def set_ramp_level(self, value):
        st.session_state.ramp_level = value

    def set_custom_campaign(self, value):
        st.session_state.custom_campaign = value

    def set_error_message(self, value):
        st.session_state.error_message = value

    def set_selected_bus(self, value):
        st.session_state.selected_bus = value

    def set_bus_slider(self, value):
        st.session_state.bus_slider = value

    def set_bus_num_input(self, value):
        st.session_state.bus_num_input = value

    def set_sim_speed(self, value):
        st.session_state.sim_speed = value

    def set_num_attacked_buses(self, value):
        st.session_state.num_attacked_buses = value

    def set_current_attack_targets(self, value):
        st.session_state.current_attack_targets = value

    def set_num_attack_slider(self, value):
        st.session_state.num_attack_slider = value

    def set_is_converged(self, value):
        st.session_state.is_converged = value

    def set_halt_on_non_convergence(self, value):
        st.session_state.halt_on_non_convergence = value

    def set_data_replay_buffer(self, value):
        st.session_state.data_replay_buffer = value

    def set_line_outage_target(self, value):
        st.session_state.line_outage_target = value

    def set_voltage_history(self, value):
        st.session_state.voltage_history = value

    def set_adaptive_campaign_intensity(self, value):
        st.session_state.adaptive_campaign_intensity = value

    def set_generated_adaptive_campaign(self, value):
        st.session_state.generated_adaptive_campaign = value