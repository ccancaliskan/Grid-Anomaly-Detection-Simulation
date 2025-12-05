use osmpbf::{ElementReader, Element};
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::error::Error;

// Function to calculate approximate distance between two lat/lon points (Haversine formula)
fn haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    const R: f64 = 6371.0; // Earth's radius in kilometers
    let d_lat = (lat2 - lat1).to_radians();
    let d_lon = (lon2 - lon1).to_radians();
    let lat1_rad = lat1.to_radians();
    let lat2_rad = lat2.to_radians();

    let a = (d_lat / 2.0).sin().powi(2) + lat1_rad.cos() * lat2_rad.cos() * (d_lon / 2.0).sin().powi(2);
    let c = 2.0 * a.sqrt().atan2((1.0 - a).sqrt());

    R * c
}

pub fn extract_grid_data(path: &str, output_dir: &str) -> Result<(), Box<dyn Error>> {
    let reader = ElementReader::from_path(path)?;

    let mut osm_power_nodes: HashMap<i64, (f64, f64, bool, bool, Option<String>, Option<String>)> = HashMap::new();
    let mut all_node_coords: HashMap<i64, (f64, f64)> = HashMap::new();
    let mut osm_power_ways: HashMap<i64, (Vec<i64>, bool, bool, Option<String>)> = HashMap::new();

    let mut element_count = 0u64;
    println!("Starting to process elements...");

    reader.for_each(|element| {
        element_count += 1;
        if element_count % 1_000_000 == 0 {
            println!("Processed {} elements...", element_count);
        }

        match element {
            Element::Node(node) => {
                all_node_coords.insert(node.id(), (node.lat(), node.lon()));
                let tags: HashMap<_, _> = node.tags().collect();
                let is_substation = tags.get("power").map_or(false, |v| *v == "substation" || *v == "station");
                let is_transformer_node = tags.get("power").map_or(false, |v| *v == "transformer");
                if is_substation || is_transformer_node {
                    osm_power_nodes.insert(node.id(), (
                        node.lat(),
                        node.lon(),
                        is_substation,
                        is_transformer_node,
                        tags.get("name").map(|s| s.to_string()),
                        tags.get("voltage").map(|s| s.to_string()),
                    ));
                }
            },
            Element::DenseNode(node) => {
                all_node_coords.insert(node.id(), (node.lat(), node.lon()));
                let tags: HashMap<_, _> = node.tags().collect();
                let is_substation = tags.get("power").map_or(false, |v| *v == "substation" || *v == "station");
                let is_transformer_node = tags.get("power").map_or(false, |v| *v == "transformer");
                 if is_substation || is_transformer_node {
                    osm_power_nodes.insert(node.id(), (
                        node.lat(),
                        node.lon(),
                        is_substation,
                        is_transformer_node,
                        tags.get("name").map(|s| s.to_string()),
                        tags.get("voltage").map(|s| s.to_string()),
                    ));
                }
            },
            Element::Way(way) => {
                let tags: HashMap<_, _> = way.tags().collect();
                let is_power_line = tags.get("power").map_or(false, |v| *v == "line" || *v == "cable");
                let is_power_transformer_way = tags.get("power").map_or(false, |v| *v == "transformer");
                if is_power_line || is_power_transformer_way {
                    osm_power_ways.insert(way.id(), (
                        way.refs().collect(),
                        is_power_line,
                        is_power_transformer_way,
                        tags.get("voltage").map(|s| s.to_string()),
                    ));
                }
            },
            _ => (),
        }
    })?;

    println!("Finished processing PBF file. Now writing to CSV files...");

    fs::create_dir_all(output_dir)?;

    let nodes_file_path = format!("{}/osm_power_nodes.csv", output_dir);
    let mut nodes_file = fs::File::create(&nodes_file_path)?;
    writeln!(nodes_file, "id,name,lat,lon,is_substation,is_transformer_node,voltage")?;
    for (id, (lat, lon, is_sub, is_trafo, name, volt)) in osm_power_nodes.iter() {
        writeln!(nodes_file, "{},\"{}\",{},{},{},{},\"{}\"", id, name.as_deref().unwrap_or(""), lat, lon, is_sub, is_trafo, volt.as_deref().unwrap_or(""))?;
    }
    println!("Exported {} power nodes to {}", osm_power_nodes.len(), nodes_file_path);
    
    let all_nodes_file_path = format!("{}/osm_all_nodes.csv", output_dir);
    let mut all_nodes_file = fs::File::create(&all_nodes_file_path)?;
    writeln!(all_nodes_file, "id,lat,lon")?;
    let mut node_count = 0;
    let total_nodes = all_node_coords.len();
    println!("Writing {} total nodes to {}...", total_nodes, all_nodes_file_path);
    for (id, (lat, lon)) in all_node_coords.iter() {
        writeln!(all_nodes_file, "{},{},{}", id, lat, lon)?;
        node_count += 1;
        if node_count % 1_000_000 == 0 {
            println!("Wrote {}/{} nodes...", node_count, total_nodes);
        }
    }
    println!("Finished writing {} total nodes.", total_nodes);

    let ways_file_path = format!("{}/osm_power_ways.csv", output_dir);
    let mut ways_file = fs::File::create(&ways_file_path)?;
    writeln!(ways_file, "id,node_ids,is_power_line,is_power_transformer_way,length_km,voltage")?;
    let mut way_count = 0;
    let total_ways = osm_power_ways.len();
    println!("Writing {} power ways to {}...", total_ways, ways_file_path);
    for (id, (node_refs, is_line, is_trafo, volt)) in osm_power_ways.iter() {
        let node_ids_str: String = node_refs.iter().map(|n| n.to_string()).collect::<Vec<_>>().join(";");
        let mut length_km = 0.0;
        for i in 0..node_refs.len().saturating_sub(1) {
            if let (Some(c1), Some(c2)) = (all_node_coords.get(&node_refs[i]), all_node_coords.get(&node_refs[i+1])) {
                length_km += haversine_distance(c1.0, c1.1, c2.0, c2.1);
            }
        }
        writeln!(ways_file, "{},\"{}\",{},{},{},\"{}\"", id, node_ids_str, is_line, is_trafo, length_km, volt.as_deref().unwrap_or(""))?;
        way_count += 1;
        if way_count % 100_000 == 0 {
            println!("Wrote {}/{} ways...", way_count, total_ways);
        }
    }
    println!("Finished writing {} power ways.", total_ways);

    Ok(())
}