import math
import pandas as pd
import pandapower as pp
import networkx as nx
import random
import os
import subprocess
import shutil

from gads.campaign_manager import generate_adaptive_campaign
from gads.config import NUM_SIMULATION_STEPS


def _parse_voltage(v_str):
    if not isinstance(v_str, str):
        return 20.0
    
    v_str = v_str.split(';')[0]
    v_str = "".join(v_str.split())
    v_str = v_str.lower()
    
    if not v_str:
        return 20.0
        
    if "kv" in v_str:
        v_str = v_str.replace("kv", "")
        try:
            return float(v_str)
        except ValueError:
            return 20.0
            
    try:
        return float(v_str) / 1000.0
    except ValueError:
        return 20.0

def _haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class SimulationState:
    GRID_MAPPING = {
        "IEEE 33 Bus": pp.networks.case33bw,
        "IEEE 14 Bus": pp.networks.case14,
        "IEEE 30 Bus": pp.networks.case30,
        "IEEE 118 Bus": pp.networks.case118,
    }

    def get_available_grids(self):
        base_grids = list(self.GRID_MAPPING.keys())
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        aachen_dir = os.path.join(project_root, "grid-importer", "output")
        if os.path.exists(os.path.join(aachen_dir, "osm_power_nodes.csv")):
            base_grids.append("Aachen (OSM)")
        custom_grid_dir = os.path.join(project_root, "grid-importer", "custom_grid")
        if os.path.exists(os.path.join(custom_grid_dir, "osm_power_nodes.csv")):
            base_grids.append("Custom (Uploaded)")
        return base_grids

    def __init__(self, grid_type="IEEE 33 Bus"):
        self.is_running = False
        self.time_step = 0
        self.grid_type = grid_type
        self.data = pd.DataFrame(columns=['time_step', 'bus_id', 'vm_pu', 'is_attacked'])
        
        if grid_type == "Aachen (OSM)":
            self.net = self._load_osm_grid("output")
        elif grid_type == "Custom (Uploaded)":
            self.net = self._load_osm_grid("custom_grid")
        elif grid_type in self.GRID_MAPPING:
            self.net = self.GRID_MAPPING[grid_type]()
        else:
            self.grid_type = "IEEE 33 Bus"
            self.net = self.GRID_MAPPING[self.grid_type]()

        self._ensure_geodata()
        self.original_loads = self.net.load.p_mw.copy() if not self.net.load.empty else pd.Series(dtype=float)
        
        try:
            if self.net.res_bus.empty and len(self.net.bus) > 0:
                pp.runpp(self.net)
        except Exception as e:
            self.error_message = f"Initial power flow failed for {grid_type}: {e}"
        
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
        self.voltage_history = []
        self.adaptive_campaign_intensity = 1
        self.generated_adaptive_campaign = []
        self.generated_adaptive_campaign_intensity = 0

    def _ensure_geodata(self):
        if ('bus_geodata' in self.net and not self.net.bus_geodata.empty) or len(self.net.bus) == 0:
            return
        mg = pp.topology.create_nxgraph(self.net)
        pos = nx.spring_layout(mg, dim=2, seed=42) if mg.number_of_nodes() > 0 else {i: (i % 5, i // 5) for i in self.net.bus.index}
        coords_df = pd.DataFrame.from_dict(pos, orient='index', columns=['x', 'y'])
        self.net.bus_geodata = coords_df.reindex(self.net.bus.index)

    def _ensure_std_types(self, net):
        line_types = {
            "NAYY 4x50 SE": {"c_nf_per_km": 210, "r_ohm_per_km": 0.641, "x_ohm_per_km": 0.083, "max_i_ka": 0.142, "type": "cs"},
            "490-AL1/80-ST1A 110.0": {"c_nf_per_km": 10.4, "r_ohm_per_km": 0.058, "x_ohm_per_km": 0.41, "max_i_ka": 0.8, "type": "ol"},
            "NA2XS2Y 1x240 RM/25 12/20 kV": {"c_nf_per_km": 140, "r_ohm_per_km": 0.125, "x_ohm_per_km": 0.118, "max_i_ka": 0.44, "type": "cs"}
        }
        for name, data in line_types.items():
            if name not in net.std_types["line"]:
                pp.create_std_type(net, name=name, data=data, element='line')

    def run_importer(self, pbf_path, output_folder_name):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        # ... (rest of the function is the same)
        grid_importer_dir = os.path.join(project_root, "grid-importer")
        output_dir = os.path.join(grid_importer_dir, output_folder_name)
        rust_exe_path = os.path.join(grid_importer_dir, "target", "debug", "grid-importer")
        try:
            os.makedirs(output_dir, exist_ok=True)
            cmd = [rust_exe_path, pbf_path, output_dir]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True, f"Successfully processed file. {result.stdout}"
        except Exception as e:
            return False, f"An error occurred: {e}"

    def delete_osm_grid(self, folder_name):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        grid_dir = os.path.join(project_root, "grid-importer", folder_name)
        try:
            if os.path.exists(grid_dir):
                shutil.rmtree(grid_dir)
            return True, f"Deleted grid data in '{folder_name}'."
        except Exception as e:
            return False, f"Error deleting grid data: {e}"

    
#... (rest of the file until _load_osm_grid)

# ... (inside SimulationState class)
    def _create_osm_buses(self, net, nodes_df):
        """Creates pandapower buses from OSM power node data."""
        bus_nodes = nodes_df[nodes_df['is_substation'] | nodes_df['is_transformer_node']].copy()
        if bus_nodes.empty:
            self.error_message = "No substations or transformers found in OSM data to create buses."
            return None, None

        bus_id_map = {row['id']: pp.create_bus(net, name=row['name'] or str(row['id']), vn_kv=_parse_voltage(row['voltage'])) for _, row in bus_nodes.iterrows()}
        for osm_id, pp_id in bus_id_map.items():
            row = bus_nodes[bus_nodes['id'] == osm_id].iloc[0]
            net.bus_geodata.loc[pp_id] = [row['lon'], row['lat']]
        return bus_id_map, bus_nodes

    def _create_osm_lines(self, net, bus_nodes, bus_id_map):
        """Creates pandapower lines using a Minimum Spanning Tree approach."""
        # Create a complete graph of all buses
        G = nx.Graph()
        bus_nodes_list = list(bus_nodes.iterrows())
        for i in range(len(bus_nodes_list)):
            _, bus1 = bus_nodes_list[i]
            G.add_node(bus1['id'])
            for j in range(i + 1, len(bus_nodes_list)):
                _, bus2 = bus_nodes_list[j]
                dist = _haversine_distance(bus1['lat'], bus1['lon'], bus2['lat'], bus2['lon'])
                G.add_edge(bus1['id'], bus2['id'], weight=dist)

        # Compute the minimum spanning tree
        mst = nx.minimum_spanning_tree(G)

        # Add some of the shortest edges back to create loops
        edges_by_weight = sorted(G.edges(data=True), key=lambda t: t[2].get('weight', 1))
        num_extra_edges = int(len(mst.edges) * 0.2) # Add 20% more edges
        
        for u, v, data in edges_by_weight:
            if num_extra_edges == 0:
                break
            if not mst.has_edge(u, v):
                mst.add_edge(u, v, **data)
                num_extra_edges -= 1

        # Create lines from the enhanced MST
        for u, v, data in mst.edges(data=True):
            length = data['weight']
            v_u = _parse_voltage(bus_nodes[bus_nodes.id==u].iloc[0].voltage)
            v_v = _parse_voltage(bus_nodes[bus_nodes.id==v].iloc[0].voltage)
            vn_kv = max(v_u, v_v)
            
            r_ohm_per_km = 0.1
            x_ohm_per_km = 0.1
            c_nf_per_km = 10.0
            max_i_ka = 0.5

            if vn_kv > 30: # Transmission
                r_ohm_per_km = 0.05
                x_ohm_per_km = 0.3

            pp.create_line_from_parameters(net, from_bus=bus_id_map[u], to_bus=bus_id_map[v], length_km=max(length, 0.01), 
                                            r_ohm_per_km=r_ohm_per_km, x_ohm_per_km=x_ohm_per_km, c_nf_per_km=c_nf_per_km, max_i_ka=max_i_ka)

    def _setup_osm_grid_defaults(self, net):
        """Creates a slack bus and default loads for the OSM grid."""
        if len(net.bus) > 0:
            hv_buses = net.bus[net.bus.vn_kv >= 110]
            slack_bus = hv_buses.index[0] if not hv_buses.empty else net.bus.index[0]
            pp.create_ext_grid(net, bus=slack_bus, vm_pu=1.0)
            # Create small loads on all non-slack buses to ensure connectivity
            for bus_id in net.bus.index:
                if bus_id != slack_bus:
                    pp.create_load(net, bus=bus_id, p_mw=0.001, q_mvar=0.0005)

    def _load_osm_grid(self, output_folder) -> pp.pandapowerNet:
        net = pp.create_empty_network()
        self._ensure_std_types(net)
        net.bus_geodata = pd.DataFrame(columns=['x', 'y'])
        
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        output_dir = os.path.join(project_root, "grid-importer", output_folder)
        nodes_csv_path = os.path.join(output_dir, "osm_power_nodes.csv")
        all_nodes_csv_path = os.path.join(output_dir, "osm_all_nodes.csv")

        if not (os.path.exists(nodes_csv_path) and os.path.exists(all_nodes_csv_path)):
            self.error_message = f"CSV files not found in {output_dir}."
            return net

        nodes_df = pd.read_csv(nodes_csv_path).fillna('')
        
        bus_id_map, bus_nodes = self._create_osm_buses(net, nodes_df)
        if bus_id_map is None:
            return net
        
        self._create_osm_lines(net, bus_nodes, bus_id_map)
        self._setup_osm_grid_defaults(net)
        
        return net

    def generate_and_store_campaign(self):
        self.generated_adaptive_campaign = generate_adaptive_campaign(self.adaptive_campaign_intensity, self.net, NUM_SIMULATION_STEPS)

    def export_data_to_csv(self):
        file_path = "simulation_ground_truth.csv"
        self.data.to_csv(file_path, index=False)
        return file_path
