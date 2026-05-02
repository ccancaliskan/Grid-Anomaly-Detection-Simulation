use std::env;
use grid_importer::extract_grid_data;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!(
            "Usage: {} <path_to_pbf_file> <output_directory>",
            args[0]
        );
        eprintln!("  <path_to_pbf_file>    Path to an .osm.pbf file to parse.");
        eprintln!("  <output_directory>    Directory where CSV output files will be written.");
        std::process::exit(1);
    }

    let pbf_path = &args[1];
    let output_dir = &args[2];

    println!("Grid Importer");
    println!("  Input : {}", pbf_path);
    println!("  Output: {}", output_dir);

    if let Err(e) = extract_grid_data(pbf_path, output_dir) {
        eprintln!("Error: {}", e);
        std::process::exit(1);
    }

    println!("Done.");
}
