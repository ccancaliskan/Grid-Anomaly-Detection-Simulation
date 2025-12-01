import networkx as nx
import matplotlib.pyplot as plt

def create_grid(num_nodes=50):
    # Seed ensures the graph looks the same every time you run it
    G = nx.barabasi_albert_graph(num_nodes, 2, seed=42) 
    return G
# Test it
grid = create_grid()
print(f"Grid generated with {grid.number_of_nodes()} nodes.")
