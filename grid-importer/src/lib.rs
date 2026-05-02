use osmpbf::{ElementReader, Element};
use std::collections::HashMap;
use std::fs;
use std::io::Write;
use std::error::Error;

/// Approximate great-circle distance between two (lat, lon) points (km).
fn haversine_distance(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    const R: f64 = 6_371.0;
    let d_lat = (lat2 - lat1).to_radians();
    let d_lon = (lon2 - lon1).to_radians();
    let a = (d_lat / 2.0).sin().powi(2)
        + lat1.to_radians().cos() * lat2.to_radians().cos() * (d_lon / 2.0).sin().powi(2);
    R * 2.0 * a.sqrt().atan2((1.0 - a).sqrt())
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// (lat, lon, is_substation, is_transformer, name, voltage)
type PowerNodeData = (f64, f64, bool, bool, Option<String>, Option<String>);

/// (node_refs, is_power_line, is_power_transformer_way, voltage)
type PowerWayData = (Vec<i64>, bool, bool, Option<String>);

// ---------------------------------------------------------------------------
// Tag helpers — avoid per-element HashMap allocation
// ---------------------------------------------------------------------------

fn tag_value<'a>(tags: &mut impl Iterator<Item = (&'a str, &'a str)>, key: &str) -> Option<String> {
    tags.find(|(k, _)| *k == key).map(|(_, v)| v.to_string())
}

/// Check whether any tag matches `key == value` without collecting into a HashMap.
fn tag_equals<'a>(mut tags: impl Iterator<Item = (&'a str, &'a str)>, key: &str, values: &[&str]) -> bool {
    tags.any(|(k, v)| k == key && values.contains(&v))
}

// ---------------------------------------------------------------------------
// Main extraction function
// ---------------------------------------------------------------------------

pub fn extract_grid_data(path: &str, output_dir: &str) -> Result<(), Box<dyn Error>> {
    let reader = ElementReader::from_path(path)?;

    // node_id → (lat, lon, is_substation, is_transformer, name, voltage)
    let mut power_nodes: HashMap<i64, PowerNodeData> = HashMap::new();
    // node_id → (lat, lon)  — all nodes, used for way length calculation
    let mut all_coords: HashMap<i64, (f64, f64)> = HashMap::new();
    // way_id → (refs, is_line, is_transformer_way, voltage)
    let mut power_ways: HashMap<i64, PowerWayData> = HashMap::new();

    let mut element_count = 0u64;
    println!("Starting to process elements…");

    reader.for_each(|element| {
        element_count += 1;
        if element_count % 1_000_000 == 0 {
            println!("  Processed {} elements…", element_count);
        }

        match element {
            Element::Node(node) => {
                all_coords.insert(node.id(), (node.lat(), node.lon()));
                let mut tags = node.tags();
                if let Some(power_val) = tag_value(&mut tags, "power") {
                    let is_sub  = matches!(power_val.as_str(), "substation" | "station");
                    let is_traf = power_val == "transformer";
                    if is_sub || is_traf {
                        // Re-iterate tags for name/voltage (iterators are single-pass)
                        let name    = node.tags().find(|(k, _)| *k == "name")   .map(|(_, v)| v.to_string());
                        let voltage = node.tags().find(|(k, _)| *k == "voltage").map(|(_, v)| v.to_string());
                        power_nodes.insert(node.id(), (node.lat(), node.lon(), is_sub, is_traf, name, voltage));
                    }
                }
            }

            Element::DenseNode(node) => {
                all_coords.insert(node.id(), (node.lat(), node.lon()));
                let mut tags = node.tags();
                if let Some(power_val) = tag_value(&mut tags, "power") {
                    let is_sub  = matches!(power_val.as_str(), "substation" | "station");
                    let is_traf = power_val == "transformer";
                    if is_sub || is_traf {
                        let name    = node.tags().find(|(k, _)| *k == "name")   .map(|(_, v)| v.to_string());
                        let voltage = node.tags().find(|(k, _)| *k == "voltage").map(|(_, v)| v.to_string());
                        power_nodes.insert(node.id(), (node.lat(), node.lon(), is_sub, is_traf, name, voltage));
                    }
                }
            }

            Element::Way(way) => {
                let mut tags = way.tags();
                if let Some(power_val) = tag_value(&mut tags, "power") {
                    let is_line = matches!(power_val.as_str(), "line" | "cable");
                    let is_traf = power_val == "transformer";
                    if is_line || is_traf {
                        let voltage = way.tags().find(|(k, _)| *k == "voltage").map(|(_, v)| v.to_string());
                        power_ways.insert(way.id(), (way.refs().collect(), is_line, is_traf, voltage));
                    }
                }
            }

            _ => {}
        }
    })?;

    println!("Finished reading PBF ({} elements total). Writing CSV files…", element_count);
    fs::create_dir_all(output_dir)?;

    // --- Power nodes ---
    let nodes_path = format!("{}/osm_power_nodes.csv", output_dir);
    {
        let mut f = fs::File::create(&nodes_path)?;
        writeln!(f, "id,name,lat,lon,is_substation,is_transformer_node,voltage")?;
        for (id, (lat, lon, is_sub, is_traf, name, volt)) in &power_nodes {
            writeln!(
                f,
                "{},\"{}\",{},{},{},{},\"{}\"",
                id,
                name.as_deref().unwrap_or(""),
                lat, lon, is_sub, is_traf,
                volt.as_deref().unwrap_or("")
            )?;
        }
    }
    println!("Exported {} power nodes → {}", power_nodes.len(), nodes_path);

    // --- All node coordinates ---
    let all_nodes_path = format!("{}/osm_all_nodes.csv", output_dir);
    {
        let mut f = fs::File::create(&all_nodes_path)?;
        writeln!(f, "id,lat,lon")?;
        let total = all_coords.len();
        for (i, (id, (lat, lon))) in all_coords.iter().enumerate() {
            writeln!(f, "{},{},{}", id, lat, lon)?;
            if (i + 1) % 1_000_000 == 0 {
                println!("  Wrote {}/{} coordinate nodes…", i + 1, total);
            }
        }
    }
    println!("Exported {} coordinate nodes → {}", all_coords.len(), all_nodes_path);

    // --- Power ways ---
    let ways_path = format!("{}/osm_power_ways.csv", output_dir);
    {
        let mut f = fs::File::create(&ways_path)?;
        writeln!(f, "id,node_ids,is_power_line,is_power_transformer_way,length_km,voltage")?;
        let total = power_ways.len();
        for (i, (id, (refs, is_line, is_traf, volt))) in power_ways.iter().enumerate() {
            let node_ids_str = refs.iter()
                .map(|n| n.to_string())
                .collect::<Vec<_>>()
                .join(";");

            let length_km: f64 = refs.windows(2).map(|w| {
                match (all_coords.get(&w[0]), all_coords.get(&w[1])) {
                    (Some(&(la1, lo1)), Some(&(la2, lo2))) => haversine_distance(la1, lo1, la2, lo2),
                    _ => 0.0,
                }
            }).sum();

            writeln!(
                f,
                "{},\"{}\",{},{},{:.4},\"{}\"",
                id, node_ids_str, is_line, is_traf, length_km,
                volt.as_deref().unwrap_or("")
            )?;

            if (i + 1) % 100_000 == 0 {
                println!("  Wrote {}/{} power ways…", i + 1, total);
            }
        }
    }
    println!("Exported {} power ways → {}", power_ways.len(), ways_path);

    Ok(())
}
