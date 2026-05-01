import math
import os
import shutil
import subprocess

import networkx as nx
import pandas as pd
import pandapower as pp

from gads.campaign_manager import generate_adaptive_campaign
from gads.config import NUM_SIMULATION_STEPS


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions, no state dependency)
# ---------------------------------------------------------------------------

def _parse_voltage(v_str) -> float:
    """Parse an OSM voltage string (e.g. '110kV', '110000') into kV float."""
    if not isinstance(v_str, str):
        return 20.0

    v_str = v_str.split(";")[0]
    v_str = "".join(v_str.split()).lower()

    if not v_str:
        return 20.0

    if "kv" in v_str:
        try:
            return float(v_str.replace("kv", ""))
        except ValueError:
            return 20.0

    try:
        raw = float(v_str)
        # Values above 1000 are assumed to be in volts → convert to kV
        return raw / 1000.0 if raw > 1000 else raw
    except ValueError:
        return 20.0


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two (lat, lon) points."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# SimulationState
# ---------------------------------------------------------------------------

class SimulationState:
    GRID_MAPPING = {
        "IEEE 33 Bus": pp.networks.case33bw,
        "IEEE 14 Bus": pp.networks.case14,
        "IEEE 30 Bus": pp.networks.case30,
        "IEEE 118 Bus": pp.networks.case118,
    }

    # ------------------------------------------------------------------
    # Grid discovery helpers
    # ------------------------------------------------------------------

    def _project_root(self) -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

    def get_available_grids(self) -> list[str]:
        base = list(self.GRID_MAPPING.keys())
        root = self._project_root()
        if os.path.exists(os.path.join(root, "grid-importer", "output", "osm_power_nodes.csv")):
            base.append("Aachen (OSM)")
        if os.path.exists(os.path.join(root, "grid-importer", "custom_grid", "osm_power_nodes.csv")):
            base.append("Custom (Uploaded)")
        return base

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, grid_type: str = "IEEE 33 Bus") -> None:
        # Simulation bookkeeping
        self.is_running: bool = False
        self.time_step: int = 0
        self.error_message: str = ""  # must exist before any method that sets it

        # Grid
        self.grid_type = grid_type
        self.net = self._load_grid(grid_type)
        self._ensure_geodata()

        self.original_loads: pd.Series = (
            self.net.load.p_mw.copy() if not self.net.load.empty else pd.Series(dtype=float)
        )

        # Run initial power flow so the network plot is populated on first render
        try:
            if len(self.net.bus) > 0:
                pp.runpp(self.net)
        except Exception as exc:
            self.error_message = f"Initial power flow failed for '{grid_type}': {exc}"

        # Data storage
        self.data: pd.DataFrame = pd.DataFrame(
            columns=["time_step", "bus_id", "vm_pu", "is_attacked"]
        )
        # voltage_history stores pd.Series(index=bus_ids) so bus lookup is O(1)
        self.voltage_history: list[pd.Series] = []

        # Attack parameters
        self.attack_type: str = "None"
        self.liar_intensity: float = 1.1
        self.overload_intensity: float = 3.0
        self.flicker_intensity: float = 2.0
        self.stealth_intensity: float = 0.95
        self.ramp_rate: float = 0.1
        self.ramp_level: float = 1.0

        # Target tracking
        self.num_attack_slider: int = 1
        self.num_attacked_buses: int = 1
        self.current_attack_targets: list = []

        # Campaign state
        self.custom_campaign: list[dict] = []
        self.adaptive_campaign_intensity: int = 1
        self.generated_adaptive_campaign: list[dict] = []
        self.generated_adaptive_campaign_intensity: int = 0
        self.data_replay_buffer: pd.Series | None = None

        # UI / display
        self.selected_bus: int = 0
        self.bus_slider: int = 0
        self.bus_num_input: int = 0
        self.sim_speed: float = 0.1
        self.is_converged: bool = True
        self.halt_on_non_convergence: bool = False

    # ------------------------------------------------------------------
    # Grid loading
    # ------------------------------------------------------------------

    def _load_grid(self, grid_type: str):
        if grid_type == "Aachen (OSM)":
            return self._load_osm_grid("output")
        if grid_type == "Custom (Uploaded)":
            return self._load_osm_grid("custom_grid")
        if grid_type in self.GRID_MAPPING:
            return self.GRID_MAPPING[grid_type]()
        # Fallback
        self.grid_type = "IEEE 33 Bus"
        return self.GRID_MAPPING[self.grid_type]()

    def _ensure_geodata(self) -> None:
        """Generate spring-layout geodata when the network lacks coordinates."""
        if (
            "bus_geodata" in self.net
            and not self.net.bus_geodata.empty
        ) or len(self.net.bus) == 0:
            return

        mg = pp.topology.create_nxgraph(self.net)
        if mg.number_of_nodes() > 0:
            pos = nx.spring_layout(mg, dim=2, seed=42)
        else:
            pos = {i: (i % 5, i // 5) for i in self.net.bus.index}

        self.net.bus_geodata = pd.DataFrame.from_dict(
            pos, orient="index", columns=["x", "y"]
        ).reindex(self.net.bus.index)

    # ------------------------------------------------------------------
    # OSM grid construction
    # ------------------------------------------------------------------

    def _ensure_std_types(self, net) -> None:
        """Register custom line standard types if they are missing."""
        line_types = {
            "NAYY 4x50 SE": {
                "c_nf_per_km": 210, "r_ohm_per_km": 0.641,
                "x_ohm_per_km": 0.083, "max_i_ka": 0.142, "type": "cs",
            },
            "490-AL1/80-ST1A 110.0": {
                "c_nf_per_km": 10.4, "r_ohm_per_km": 0.058,
                "x_ohm_per_km": 0.41, "max_i_ka": 0.8, "type": "ol",
            },
            "NA2XS2Y 1x240 RM/25 12/20 kV": {
                "c_nf_per_km": 140, "r_ohm_per_km": 0.125,
                "x_ohm_per_km": 0.118, "max_i_ka": 0.44, "type": "cs",
            },
        }
        for name, data in line_types.items():
            if name not in net.std_types["line"]:
                pp.create_std_type(net, name=name, data=data, element="line")

    def _create_osm_buses(self, net, nodes_df: pd.DataFrame):
        """Creates pandapower buses from OSM power-node data."""
        bus_nodes = nodes_df[
            nodes_df["is_substation"] | nodes_df["is_transformer_node"]
        ].copy()

        if bus_nodes.empty:
            self.error_message = "No substations or transformers found in OSM data."
            return None, None

        bus_id_map: dict[int, int] = {}
        for _, row in bus_nodes.iterrows():
            pp_id = pp.create_bus(
                net,
                name=row["name"] or str(row["id"]),
                vn_kv=_parse_voltage(row["voltage"]),
            )
            bus_id_map[row["id"]] = pp_id
            net.bus_geodata.loc[pp_id] = [row["lon"], row["lat"]]

        return bus_id_map, bus_nodes

    def _create_osm_lines(self, net, bus_nodes: pd.DataFrame, bus_id_map: dict) -> None:
        """Connects buses via a minimum-spanning-tree + 20 % extra edges."""
        G: nx.Graph = nx.Graph()
        bus_list = list(bus_nodes.iterrows())

        for i, (_, b1) in enumerate(bus_list):
            G.add_node(b1["id"])
            for _, b2 in bus_list[i + 1:]:
                dist = _haversine_distance(b1["lat"], b1["lon"], b2["lat"], b2["lon"])
                G.add_edge(b1["id"], b2["id"], weight=dist)

        mst: nx.Graph = nx.minimum_spanning_tree(G)

        # Add shortest non-MST edges back to create mesh loops
        extra = int(len(mst.edges) * 0.2)
        for u, v, data in sorted(G.edges(data=True), key=lambda e: e[2].get("weight", 1)):
            if extra == 0:
                break
            if not mst.has_edge(u, v):
                mst.add_edge(u, v, **data)
                extra -= 1

        for u, v, data in mst.edges(data=True):
            length = data["weight"]
            v_u = _parse_voltage(bus_nodes[bus_nodes.id == u].iloc[0].voltage)
            v_v = _parse_voltage(bus_nodes[bus_nodes.id == v].iloc[0].voltage)
            vn_kv = max(v_u, v_v)

            if vn_kv > 30:  # Transmission line parameters
                r, x = 0.05, 0.3
            else:           # Distribution line parameters
                r, x = 0.1, 0.1

            pp.create_line_from_parameters(
                net,
                from_bus=bus_id_map[u],
                to_bus=bus_id_map[v],
                length_km=max(length, 0.01),
                r_ohm_per_km=r,
                x_ohm_per_km=x,
                c_nf_per_km=10.0,
                max_i_ka=0.5,
            )

    def _setup_osm_grid_defaults(self, net) -> None:
        """Attach a slack bus and small default loads to the OSM grid."""
        if len(net.bus) == 0:
            return
        hv = net.bus[net.bus.vn_kv >= 110]
        slack = hv.index[0] if not hv.empty else net.bus.index[0]
        pp.create_ext_grid(net, bus=slack, vm_pu=1.0)
        for bus_id in net.bus.index:
            if bus_id != slack:
                pp.create_load(net, bus=bus_id, p_mw=0.001, q_mvar=0.0005)

    def _load_osm_grid(self, output_folder: str):
        net = pp.create_empty_network()
        self._ensure_std_types(net)
        net.bus_geodata = pd.DataFrame(columns=["x", "y"])

        root = self._project_root()
        output_dir = os.path.join(root, "grid-importer", output_folder)
        nodes_path = os.path.join(output_dir, "osm_power_nodes.csv")
        all_nodes_path = os.path.join(output_dir, "osm_all_nodes.csv")

        if not (os.path.exists(nodes_path) and os.path.exists(all_nodes_path)):
            self.error_message = f"CSV files not found in {output_dir}."
            return net

        nodes_df = pd.read_csv(nodes_path).fillna("")
        bus_id_map, bus_nodes = self._create_osm_buses(net, nodes_df)
        if bus_id_map is None:
            return net

        self._create_osm_lines(net, bus_nodes, bus_id_map)
        self._setup_osm_grid_defaults(net)
        return net

    # ------------------------------------------------------------------
    # External grid importer (Rust binary)
    # ------------------------------------------------------------------

    def run_importer(self, pbf_path: str, output_folder_name: str) -> tuple[bool, str]:
        root = self._project_root()
        grid_importer_dir = os.path.join(root, "grid-importer")
        output_dir = os.path.join(grid_importer_dir, output_folder_name)
        rust_exe = os.path.join(grid_importer_dir, "target", "debug", "grid-importer")
        try:
            os.makedirs(output_dir, exist_ok=True)
            result = subprocess.run(
                [rust_exe, pbf_path, output_dir],
                capture_output=True,
                text=True,
                check=True,
            )
            return True, f"Successfully processed file. {result.stdout}"
        except subprocess.CalledProcessError as exc:
            return False, f"Importer process error: {exc.stderr}"
        except Exception as exc:
            return False, f"An error occurred: {exc}"

    def delete_osm_grid(self, folder_name: str) -> tuple[bool, str]:
        root = self._project_root()
        grid_dir = os.path.join(root, "grid-importer", folder_name)
        try:
            if os.path.exists(grid_dir):
                shutil.rmtree(grid_dir)
            return True, f"Deleted grid data in '{folder_name}'."
        except Exception as exc:
            return False, f"Error deleting grid data: {exc}"

    # ------------------------------------------------------------------
    # Campaign helpers
    # ------------------------------------------------------------------

    def generate_and_store_campaign(self) -> None:
        self.generated_adaptive_campaign = generate_adaptive_campaign(
            self.adaptive_campaign_intensity, self.net, NUM_SIMULATION_STEPS
        )
        self.generated_adaptive_campaign_intensity = self.adaptive_campaign_intensity

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_data_to_csv(self, path: str = "simulation_ground_truth.csv") -> str:
        self.data.to_csv(path, index=False)
        return path
