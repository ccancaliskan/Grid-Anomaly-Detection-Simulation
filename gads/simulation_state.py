import math
import pandas as pd
import pandapower as pp
import networkx as nx
import random
import os
import subprocess
import re

from gads.campaign_manager import generate_adaptive_campaign
from gads.config import NUM_SIMULATION_STEPS


def _parse_voltage(v_str):
    """
    Parses a voltage string from OSM (e.g., "20kV", "110000", "0.4kV") into a float in kV.
    Returns a default value if parsing fails.
    """
    if not isinstance(v_str, str):
        return 0.4  # Default to low voltage

    v_str = v_str.lower().replace(" ", "")
    if "kv" in v_str:
        try:
            return float(v_str.replace("kv", ""))
        except ValueError:
            return 0.4
    try:
        # Assume volts if no unit, then convert to kV
        return float(v_str) / 1000.0
    except ValueError:
        return 0.4

class SimulationState:
    """A pure Python class to hold the entire state of the simulation."""

    GRID_MAPPING = {
        "IEEE 33 Bus": pp.networks.case33bw,
        "IEEE 14 Bus": pp.networks.case14,
        "IEEE 30 Bus": pp.networks.case30,
        "IEEE 118 Bus": pp.networks.case118,
        "Aachen (OSM)": lambda self: self._load_aachen_osm_grid(),
    }

    def __init__(self, grid_type="IEEE 33 Bus"):
        self.is_running = False
        self.time_step = 0
        self.grid_type = grid_type
        self.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu', 'is_attacked'])
        
        # Load the grid
        self.net = self.GRID_MAPPING[grid_type](self) if grid_type == "Aachen (OSM)" else self.GRID_MAPPING[grid_type]()
        
        # Generate geo-data if it doesn't exist
        self._ensure_geodata()
        
        self.original_loads = self.net.load.p_mw.copy()
        
        try:
            if self.net.res_bus.empty:
                pp.runpp(self.net)
        except Exception:
            # Power flow may not converge for all grids initially
            pass

        # UI and Attack State
        self.attack_type = "None"
        self.liar_intensity = 1.1
        self.overload_intensity = 3.0
        self.flicker_intensity = 2.0
        self.stealth_intensity = 1.01
        self.ramp_rate = 0.1
        self.ramp_level = 1.0
        self.custom_campaign = []
        self.error_message = ""
        self.selected_bus = 0
        self.bus_slider = 0
        self.bus_num_input = 0
        self.sim_speed = 0.1
        self.num_attacked_buses = 1
        self.current_attack_targets = []
        self.num_attack_slider = 1
        self.is_converged = True
        self.halt_on_non_convergence = False
        self.data_replay_buffer = None
        self.line_outage_target = None
        self.voltage_history = []
        self.adaptive_campaign_intensity = 1
        self.generated_adaptive_campaign = []

    def _ensure_geodata(self):
        if 'bus_geodata' in self.net and not self.net.bus_geodata.empty:
            return

        mg = pp.topology.create_nxgraph(self.net)
        if mg.number_of_nodes() == 0:
            num_buses = len(self.net.bus)
            side_length = math.ceil(math.sqrt(num_buses))
            coords_dict = {i: (i % side_length, i // side_length) for i in self.net.bus.index}
        else:
            coords_dict = nx.spring_layout(mg, dim=2, seed=42)

        coords_df = pd.DataFrame.from_dict(coords_dict, orient='index', columns=['x', 'y'])
        self.net.bus_geodata = coords_df.reindex(self.net.bus.index)


    def _load_aachen_osm_grid(self) -> pp.pandapowerNet:
        net = pp.create_empty_network()
        pbf_file_name = "Aachen.osm.pbf"
        
        current_dir = os.path.dirname(__file__)
        project_root = os.path.abspath(os.path.join(current_dir, os.pardir)) # gads is a package now
        grid_importer_dir = os.path.join(project_root, "grid-importer")
        pbf_path = os.path.join(grid_importer_dir, pbf_file_name)
        output_dir = os.path.join(grid_importer_dir, "output")
        rust_exe_path = os.path.join(grid_importer_dir, "target", "debug", "grid-importer")
        
        nodes_csv_path = os.path.join(output_dir, "osm_power_nodes.csv")
        ways_csv_path = os.path.join(output_dir, "osm_power_ways.csv")

        if not os.path.exists(nodes_csv_path) or not os.path.exists(ways_csv_path):
            try:
                os.makedirs(output_dir, exist_ok=True)
                cmd = [rust_exe_path, pbf_path, output_dir]
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            except Exception as e:
                print(f"Could not run Rust importer: {e}")
                return net

        try:
            nodes_df = pd.read_csv(nodes_csv_path).fillna('')
            ways_df = pd.read_csv(ways_csv_path, sep=',', dtype={'node_ids': str}).fillna('')
        except Exception as e:
            print(f"Could not read generated CSVs: {e}")
            return net

        bus_id_map = {}
        # Create buses with voltage levels
        for _, row in nodes_df[nodes_df['is_substation']].iterrows():
            vn_kv = _parse_voltage(row['voltage'])
            pp_bus_id = pp.create_bus(net, name=row['name'] if pd.notna(row['name']) else str(row['id']), vn_kv=vn_kv)
            bus_id_map[row['id']] = pp_bus_id
            net.bus_geodata.loc[pp_bus_id] = [row['lon'], row['lat']]

        # Create lines with standard types based on voltage
        for _, row in ways_df[ways_df['is_power_line']].iterrows():
            osm_node_ids = [int(n) for n in row['node_ids'].split(';')]
            from_bus_osm = next((nid for nid in osm_node_ids if nid in bus_id_map), None)
            to_bus_osm = next((nid for nid in reversed(osm_node_ids) if nid in bus_id_map), None)

            if from_bus_osm and to_bus_osm and from_bus_osm != to_bus_osm:
                vn_kv = _parse_voltage(row['voltage'])
                std_type = "NAYY 4x50 SE" # LV Cable
                if vn_kv > 10:
                    std_type = "N2XS(FL)2Y 1x120 RM/35 64/110 kV" # HV Cable
                elif vn_kv > 1:
                    std_type = "NA2XS2Y 1x240 RM/25 12/20 kV" # MV Cable
                
                pp.create_line(net, bus_id_map[from_bus_osm], bus_id_map[to_bus_osm], length_km=row['length_km'], std_type=std_type)

        # Place external grid at a high-voltage bus
        if len(net.bus) > 0:
            hv_buses = net.bus[net.bus.vn_kv >= 110]
            slack_bus = hv_buses.index[0] if not hv_buses.empty else net.bus.index[0]
            pp.create_ext_grid(net, bus=slack_bus, vm_pu=1.0)
            
            # Add loads to low-voltage buses
            lv_buses = net.bus[net.bus.vn_kv < 1.0]
            for bus_id in lv_buses.index:
                if bus_id != slack_bus:
                    pp.create_load(net, bus=bus_id, p_mw=0.01)

        return net


    def generate_and_store_campaign(self):
        self.generated_adaptive_campaign = generate_adaptive_campaign(self.adaptive_campaign_intensity, self.net, NUM_SIMULATION_STEPS)

    def export_data_to_csv(self):
        file_path = "simulation_ground_truth.csv"
        self.data.to_csv(file_path, index=False)
        return file_path