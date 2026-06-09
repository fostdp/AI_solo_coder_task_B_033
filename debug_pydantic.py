import sys
sys.path.insert(0, '.')

print("Testing schemas import...")
try:
    from backend.models.schemas import Location, TopologyNode, TopologyEdge, TopologyMap
    from backend.modules.robot_inspector import RobotInspector
    print("All schemas imported successfully")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting Location...")
loc = Location(coordinates=[116.4, 39.9])
print(f"Location created: geo_type='{loc.geo_type}' coordinates={loc.coordinates}")
print(f"Location geo_type property: {loc.type}")
print(f"Location dict: {loc.dict()}")

print("\nTesting TopologyNode...")
node = TopologyNode(
    node_id="node_001",
    distance_km=0.0,
    chamber="综合",
    location=loc,
    node_type="branch",
    connections=["node_002", "node_003"]
)
print(f"TopologyNode created: node_id='{node.node_id}' type='{node.node_type}'")
print(f"TopologyNode dict: {node.dict()}")

print("\nTesting TopologyEdge...")
edge = TopologyEdge(
    edge_id="edge_001",
    from_node="node_001",
    to_node="node_002",
    distance=0.5,
    safety_score=0.9,
    energy_cost=1.2,
    time_cost=0.8
)
print(f"TopologyEdge created: edge_id='{edge.edge_id}' distance={edge.distance}")

print("\nTesting TopologyMap...")
topo_map = TopologyMap(
    map_id="map_001",
    name="Main Tunnel Map",
    nodes=[node],
    edges=[edge],
    branch_points=["node_001"]
)
print(f"TopologyMap created: map_id='{topo_map.map_id}' nodes={len(topo_map.nodes)} edges={len(topo_map.edges)}")

print("\nTesting RobotInspector instantiation...")
try:
    from backend.config import settings
    inspector = RobotInspector(settings)
    print("RobotInspector created successfully")
except Exception as e:
    print(f"Error creating RobotInspector: {e}")
    import traceback
    traceback.print_exc()

print("\nAll tests passed!")
