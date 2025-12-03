import pandas as pd
from gads.simulation_state import SimulationState
from gads.simulation_core import run_simulation_step
from gads.attack_manager import determine_attack_status

def main():
    """
    Example script to demonstrate using the GADS simulation as a Python library.
    """
    print("--- Initializing GADS Simulation State ---")
    # 1. Create a simulation state object for a specific grid
    state = SimulationState(grid_type="IEEE 14 Bus")
    print(f"Initialized with grid: {state.grid_type}")

    # 2. Configure the simulation parameters directly on the state object
    state.attack_type = "Overload Attack"
    state.num_attack_slider = 3 # This is how the UI sets the number of targets
    print(f"Set attack type to '{state.attack_type}' with {state.num_attack_slider} targets.")

    # 3. Run the simulation for a fixed number of steps
    num_steps_to_run = 20
    print(f"\n--- Running simulation for {num_steps_to_run} steps ---")

    for i in range(num_steps_to_run):
        # The core simulation function modifies the state object in place
        run_simulation_step(state)

        # You can inspect the state at each step
        is_attacked, _, attacked_buses, _ = determine_attack_status(state)
        bus_to_monitor = 1 # Let's monitor bus 1
        
        # Access data from the simulation state
        voltage = state.net.res_bus.vm_pu.at[bus_to_monitor]
        
        print(
            f"Step {state.time_step - 1}: "
            f"Attack Active: {bool(is_attacked)} on buses {attacked_buses}, "
            f"Bus {bus_to_monitor} Voltage: {voltage:.3f} pu"
        )
    
    print("\n--- Simulation Finished ---")

    # 4. Access the collected data
    # The state object now contains all the data collected during the run
    print("\nCollected simulation data (first 5 rows):")
    
    # Set pandas display options to show all columns
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print(state.data.head())


if __name__ == "__main__":
    main()
