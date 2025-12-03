use osmpbf::{ElementReader, Element, Way, Node, DenseNode};
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::error::Error;

// Helper trait to convert f64 to radians
trait ToRadians {
    fn to_radians(self) -> Self;
}

impl ToRadians for f64 {
    fn to_radians(self) -> Self {
        self * (std::f64::consts::PI / 180.0)
    }
}

// Function to calculate approximate distance between two lat/lon points (Haversine formula)
fn haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    const R: f64 = 6_371_000.0; // Earth's radius in meters
    let d_lat = lat2.to_radians() - lat1.to_radians();
    let d_lon = lon2.to_radians() - lon1.to_radians();

    let a = (d_lat / 2.0).sin().powi(2) + lat1.to_radians().cos() * lat2.to_radians().cos() * (d_lon / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().atan2((1.0 - a).sqrt());

    R * c
}


pub fn extract_grid_data(path: &str, output_dir: &str) -> Result<(), Box<dyn Error>> {
    let reader = ElementReader::from_path(path)?;

    // Store all power-related nodes and their tags
    let mut osm_power_nodes: HashMap<i64, (f64, f64, bool, bool, Option<String>, Option<String>)> = HashMap::new(); // id -> (lat, lon, is_substation, is_transformer_node, name, voltage)
    // Store all node coordinates for length calculation (even if not power-related)
    let mut all_node_coords: HashMap<i64, (f64, f64)> = HashMap::new();
    // Store all power-related ways and their details
    let mut osm_power_ways: HashMap<i64, (Vec<i64>, bool, bool, Option<String>)> = HashMap::new(); // id -> (node_refs, is_power_line, is_power_transformer_way, voltage)

    reader.for_each(|element| {
        match element {
            Element::Node(node) => {
                all_node_coords.insert(node.id(), (node.lat(), node.lon()));
                let is_substation = node.tags().any(|tag| tag.0 == "power" && (tag.1 == "substation" || tag.1 == "station"));
                let is_transformer_node = node.tags().any(|tag| tag.0 == "power" && tag.1 == "transformer");
                if is_substation || is_transformer_node {
                    osm_power_nodes.insert(node.id(), (
                        node.lat(),
                        node.lon(),
                        is_substation,
                        is_transformer_node,
                        node.tags().find(|tag| tag.0 == "name").map(|tag| tag.1.to_string()),
                        node.tags().find(|tag| tag.0 == "voltage").map(|tag| tag.1.to_string()),
                    ));
                }
            },
            Element::DenseNode(node) => {
                all_node_coords.insert(node.id(), (node.lat(), node.lon()));
                let is_substation = node.tags().any(|tag| tag.0 == "power" && (tag.1 == "substation" || tag.1 == "station"));
                let is_transformer_node = node.tags().any(|tag| tag.0 == "power" && tag.1 == "transformer");
                if is_substation || is_transformer_node {
                    osm_power_nodes.insert(node.id(), (
                        node.lat(),
                        node.lon(),
                        is_substation,
                        is_transformer_node,
                        node.tags().find(|tag| tag.0 == "name").map(|tag| tag.1.to_string()),
                        node.tags().find(|tag| tag.0 == "voltage").map(|tag| tag.1.to_string()),
                    ));
                }
            },
            Element::Way(way) => {
                let is_power_line = way.tags().any(|tag| tag.0 == "power" && (tag.1 == "line" || tag.1 == "cable"));
                let is_power_transformer_way = way.tags().any(|tag| tag.0 == "power" && tag.1 == "transformer");
                
                if is_power_line || is_power_transformer_way {
                    osm_power_ways.insert(way.id(), (
                        way.refs().collect(), // Collect all node IDs in the way
                        is_power_line,
                        is_power_transformer_way,
                        way.tags().find(|tag| tag.0 == "voltage").map(|tag| tag.1.to_string()),
                    ));
                }
            },
            _ => (),
        }
    })?;

    // Ensure output directory exists
    fs::create_dir_all(output_dir)?;

    // Write osm_power_nodes to CSV
    let nodes_file_path = format!("{}/osm_power_nodes.csv", output_dir);
    let mut nodes_file = fs::File::create(&nodes_file_path)?;
    writeln!(nodes_file, "id,name,lat,lon,is_substation,is_transformer_node,voltage")?;
    for (&id, &(lat, lon, is_substation, is_transformer_node, ref name, ref voltage)) in osm_power_nodes.iter() {
        writeln!(nodes_file, "{},\"{}\",{},{},{},{},\"{}\"",
            id,
            name.as_deref().unwrap_or(""),
            lat,
            lon,
            is_substation,
            is_transformer_node,
            voltage.as_deref().unwrap_or("")
        )?;
    }
    println!("Exported {} power nodes to {}", osm_power_nodes.len(), nodes_file_path);

    // Write osm_power_ways to CSV
    let ways_file_path = format!("{}/osm_power_ways.csv", output_dir);
    let mut ways_file = fs::File::create(&ways_file_path)?;
    writeln!(ways_file, "id,node_ids,is_power_line,is_power_transformer_way,length_km,voltage")?;
    for (&id, &(ref node_refs, is_power_line, is_power_transformer_way, ref voltage)) in osm_power_ways.iter() {
        let node_ids_str: String = node_refs.iter().map(|&n| n.to_string()).collect::<Vec<String>>().join(";");
        
        let mut total_length_m = 0.0;
        if node_refs.len() > 1 {
            for i in 0..node_refs.len() - 1 {
                let node_id1 = node_refs[i];
                let node_id2 = node_refs[i+1];
                if let (Some(&(lat1, lon1)), Some(&(lat2, lon2))) = (all_node_coords.get(&node_id1), all_node_coords.get(&node_id2)) {
                    total_length_m += haversine_distance(lat1, lon1, lat2, lon2);
                }
            }
        }

        writeln!(ways_file, "{},\"{}\",{},{},{},\"{}\"",
            id,
            node_ids_str,
            is_power_line,
            is_power_transformer_way,
            total_length_m / 1000.0,
            voltage.as_deref().unwrap_or("")
        )?;
    }
    println!("Exported {} power ways to {}", osm_power_ways.len(), ways_file_path);

    Ok(())
}
