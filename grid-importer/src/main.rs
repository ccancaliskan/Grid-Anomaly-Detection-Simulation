use std::env;
use grid_importer::extract_grid_data;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 { // expects two arguments: pbf path and output dir
        eprintln!("Usage: {} <path_to_pbf_file> <output_directory>", args[0]);
        std::process::exit(1);
    }
    let pbf_path = &args[1];
    let output_dir = &args[2];
    println!("Extracting grid data from PBF file: {}", pbf_path);
    println!("Output directory: {}", output_dir);

    if let Err(e) = extract_grid_data(pbf_path, output_dir) {
        eprintln!("An error occurred: {}", e);
        std::process::exit(1);
    }

    println!("Processing complete. Exiting.");
    std::process::exit(0);
}
