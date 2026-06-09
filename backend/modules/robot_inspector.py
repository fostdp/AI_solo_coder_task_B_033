import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import redis.asyncio as redis
import json
import math

from backend.config import settings
from backend.models.database import (
    inspection_robots_collection,
    inspection_missions_collection,
    robot_positions_collection,
    devices_collection,
    sensor_data_collection,
    topology_map_collection,
    robot_path_plans_collection
)
from backend.models.schemas import (
    InspectionRobot,
    InspectionMission,
    Waypoint,
    RobotPosition,
    Location,
    TopologyMap,
    TopologyNode,
    TopologyEdge,
    PathPlanningResult,
    BranchStabilityResult
)

logger = logging.getLogger(__name__)


class RobotInspector:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.running = False
        self.robot_tasks: Dict[str, asyncio.Task] = {}
        self.topology_map: Optional[TopologyMap] = None
        self.branch_sensor_weights: Dict[str, float] = {
            "temperature": 0.25,
            "humidity": 0.15,
            "methane": 0.25,
            "h2s": 0.2,
            "oxygen": 0.15
        }

    async def connect_redis(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        logger.info("Robot Inspector connected to Redis")

    async def disconnect_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Robot Inspector disconnected from Redis")

    async def _get_environment_data(self, distance_km: float, chamber: str) -> Dict[str, float]:
        device_ids = await devices_collection.distinct(
            "device_id",
            {
                "type": "env_sensor",
                "chamber": chamber,
                "distance_km": {"$gte": distance_km - 0.2, "$lte": distance_km + 0.2}
            }
        )

        if not device_ids:
            return {"temperature": 25.0, "humidity": 50.0, "methane": 0.0, "h2s": 0.0, "oxygen": 20.5}

        latest_data = await sensor_data_collection.aggregate([
            {"$match": {"device_id": {"$in": device_ids}}},
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": "$device_id",
                "temperature": {"$first": "$temperature"},
                "humidity": {"$first": "$humidity"},
                "methane": {"$first": "$methane"},
                "h2s": {"$first": "$h2s"},
                "oxygen": {"$first": "$oxygen"}
            }}
        ]).to_list(length=20)

        if not latest_data:
            return {"temperature": 25.0, "humidity": 50.0, "methane": 0.0, "h2s": 0.0, "oxygen": 20.5}

        temps = [d.get("temperature", 25.0) for d in latest_data if d.get("temperature") is not None]
        hums = [d.get("humidity", 50.0) for d in latest_data if d.get("humidity") is not None]
        meths = [d.get("methane", 0.0) for d in latest_data if d.get("methane") is not None]
        h2ss = [d.get("h2s", 0.0) for d in latest_data if d.get("h2s") is not None]
        oxys = [d.get("oxygen", 20.5) for d in latest_data if d.get("oxygen") is not None]

        return {
            "temperature": sum(temps) / len(temps) if temps else 25.0,
            "humidity": sum(hums) / len(hums) if hums else 50.0,
            "methane": max(meths) if meths else 0.0,
            "h2s": max(h2ss) if h2ss else 0.0,
            "oxygen": min(oxys) if oxys else 20.5
        }

    def _is_area_safe(self, env_data: Dict[str, float]) -> Tuple[bool, str]:
        if env_data["temperature"] >= settings.ROBOT_AVOID_HIGH_TEMP:
            return False, f"高温区域 ({env_data['temperature']:.1f}°C)"
        if env_data["humidity"] >= settings.ROBOT_AVOID_HIGH_HUMIDITY:
            return False, f"高湿区域 ({env_data['humidity']:.0f}%)"
        if env_data["methane"] >= settings.ROBOT_AVOID_GAS_METHANE:
            return False, f"甲烷超标 ({env_data['methane']:.2f}%)"
        if env_data["h2s"] >= settings.ROBOT_AVOID_GAS_H2S:
            return False, f"硫化氢超标 ({env_data['h2s']:.1f}ppm)"
        return True, "安全"

    async def _get_tunnel_coordinates(self, distance_km: float) -> List[float]:
        route_doc = await devices_collection.find_one({"type": "tunnel_route"})
        if route_doc and "coordinates" in route_doc:
            coords = route_doc["coordinates"]
            idx = min(int(len(coords) * distance_km / settings.TUNNEL_LENGTH), len(coords) - 1)
            return coords[idx]

        base_lon = 116.40 + distance_km * 0.005
        base_lat = 39.90 + math.sin(distance_km * 0.5) * 0.002
        return [base_lon, base_lat]

    async def plan_path(
        self,
        robot_id: str,
        start_km: float,
        end_km: float,
        chamber: str,
        inspection_points: Optional[List[float]] = None
    ) -> InspectionMission:
        robot = await inspection_robots_collection.find_one({"robot_id": robot_id})
        if not robot:
            raise ValueError(f"Robot {robot_id} not found")

        if inspection_points is None:
            inspection_points = []
            current = start_km
            while current <= end_km:
                inspection_points.append(current)
                current += 0.5

        waypoints = []
        avoided_areas = []
        waypoint_id = 0

        for distance_km in inspection_points:
            if distance_km < start_km or distance_km > end_km:
                continue

            env_data = await self._get_environment_data(distance_km, chamber)
            is_safe, reason = self._is_area_safe(env_data)

            if not is_safe:
                avoided_areas.append({
                    "distance_km": distance_km,
                    "reason": reason,
                    "env_data": env_data
                })

                detour_offset = 0.1
                for offset in [-detour_offset, detour_offset]:
                    alt_distance = distance_km + offset
                    if start_km <= alt_distance <= end_km:
                        alt_env = await self._get_environment_data(alt_distance, chamber)
                        alt_safe, _ = self._is_area_safe(alt_env)
                        if alt_safe:
                            distance_km = alt_distance
                            break

            coords = await self._get_tunnel_coordinates(distance_km)
            waypoint = Waypoint(
                distance_km=distance_km,
                location=Location(coordinates=coords),
                action="inspect",
                estimated_time=30.0,
                waypoint_id=waypoint_id
            )
            waypoints.append(waypoint)
            waypoint_id += 1

        mission_id = f"mission_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{robot_id}"
        mission = InspectionMission(
            mission_id=mission_id,
            robot_id=robot_id,
            name=f"巡检任务 - {chamber} {start_km:.1f}-{end_km:.1f}km",
            waypoints=waypoints,
            status="pending",
            avoided_areas=avoided_areas,
            priority=1
        )

        await inspection_missions_collection.insert_one(mission.model_dump(exclude={"id"}))
        return mission

    async def start_mission(self, mission_id: str) -> bool:
        mission = await inspection_missions_collection.find_one({"mission_id": mission_id})
        if not mission:
            return False

        result = await inspection_missions_collection.update_one(
            {"mission_id": mission_id},
            {"$set": {
                "status": "running",
                "start_time": datetime.utcnow()
            }}
        )

        if result.modified_count > 0:
            robot_id = mission["robot_id"]
            await inspection_robots_collection.update_one(
                {"robot_id": robot_id},
                {"$set": {
                    "status": "on_mission",
                    "mission_id": mission_id,
                    "current_waypoint": 0,
                    "total_waypoints": len(mission["waypoints"])
                }}
            )

            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:robot:mission_start",
                    json.dumps({
                        "mission_id": mission_id,
                        "robot_id": robot_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )

        return result.modified_count > 0

    async def update_robot_position(self, position: RobotPosition) -> Dict[str, Any]:
        doc = position.dict()
        await robot_positions_collection.insert_one(doc)

        await inspection_robots_collection.update_one(
            {"robot_id": position.robot_id},
            {"$set": {
                "current_distance_km": position.distance_km,
                "location": position.location.dict(),
                "battery": position.battery,
                "status": position.status,
                "last_update": datetime.utcnow()
            }}
        )

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:robot:position",
                json.dumps({
                    "robot_id": position.robot_id,
                    "distance_km": position.distance_km,
                    "location": position.location.dict(),
                    "battery": position.battery,
                    "speed": position.speed,
                    "status": position.status,
                    "timestamp": position.timestamp.isoformat()
                })
            )

        return {"status": "success"}

    async def get_all_robots(self) -> List[Dict[str, Any]]:
        robots = await inspection_robots_collection.find().to_list(length=settings.NUM_INSPECTION_ROBOTS)
        from backend.models.database import serialize_documents
        return serialize_documents(robots)

    async def get_robot(self, robot_id: str) -> Optional[Dict[str, Any]]:
        robot = await inspection_robots_collection.find_one({"robot_id": robot_id})
        from backend.models.database import serialize_document
        return serialize_document(robot)

    async def get_active_missions(self) -> List[Dict[str, Any]]:
        missions = await inspection_missions_collection.find(
            {"status": {"$in": ["pending", "running"]}}
        ).sort("start_time", -1).to_list(length=50)
        from backend.models.database import serialize_documents
        return serialize_documents(missions)

    async def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        mission = await inspection_missions_collection.find_one({"mission_id": mission_id})
        from backend.models.database import serialize_document
        return serialize_document(mission)

    async def get_robot_trajectory(self, robot_id: str, hours: int = 1) -> List[Dict[str, Any]]:
        start_time = datetime.utcnow() - timedelta(hours=hours)
        positions = await robot_positions_collection.find({
            "robot_id": robot_id,
            "timestamp": {"$gte": start_time}
        }).sort("timestamp", 1).to_list(length=1000)
        from backend.models.database import serialize_documents
        return serialize_documents(positions)

    async def pause_robot(self, robot_id: str) -> bool:
        result = await inspection_robots_collection.update_one(
            {"robot_id": robot_id},
            {"$set": {"status": "paused"}}
        )
        return result.modified_count > 0

    async def resume_robot(self, robot_id: str) -> bool:
        result = await inspection_robots_collection.update_one(
            {"robot_id": robot_id},
            {"$set": {"status": "on_mission"}}
        )
        return result.modified_count > 0

    async def return_to_base(self, robot_id: str) -> bool:
        robot = await inspection_robots_collection.find_one({"robot_id": robot_id})
        if not robot:
            return False

        mission = await inspection_missions_collection.find_one({
            "robot_id": robot_id,
            "status": "running"
        })
        if mission:
            await inspection_missions_collection.update_one(
                {"_id": mission["_id"]},
                {"$set": {"status": "interrupted"}}
            )

        result = await inspection_robots_collection.update_one(
            {"robot_id": robot_id},
            {"$set": {
                "status": "returning",
                "mission_id": None
            }}
        )
        return result.modified_count > 0

    async def start_control_loop(self):
        self.running = True
        logger.info("Robot Inspector control loop started")

        while self.running:
            try:
                await self._process_active_missions()
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Robot Inspector control loop error: {e}")
                await asyncio.sleep(5)

        logger.info("Robot Inspector control loop stopped")

    async def _process_active_missions(self):
        active_missions = await inspection_missions_collection.find(
            {"status": "running"}
        ).to_list(length=settings.NUM_INSPECTION_ROBOTS)

        for mission in active_missions:
            await self._process_mission(mission)

    async def _process_mission(self, mission: Dict[str, Any]):
        robot_id = mission["robot_id"]
        robot = await inspection_robots_collection.find_one({"robot_id": robot_id})

        if not robot or robot["status"] not in ["on_mission", "paused"]:
            return

        if robot["status"] == "paused":
            return

        current_waypoint_idx = robot.get("current_waypoint", 0)
        waypoints = mission["waypoints"]

        if current_waypoint_idx >= len(waypoints):
            await inspection_missions_collection.update_one(
                {"_id": mission["_id"]},
                {"$set": {
                    "status": "completed",
                    "end_time": datetime.utcnow()
                }}
            )
            await inspection_robots_collection.update_one(
                {"robot_id": robot_id},
                {"$set": {
                    "status": "idle",
                    "mission_id": None,
                    "current_waypoint": None
                }}
            )

            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:robot:mission_complete",
                    json.dumps({
                        "mission_id": mission["mission_id"],
                        "robot_id": robot_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                )
            return

        current_waypoint = waypoints[current_waypoint_idx]

        position = RobotPosition(
            robot_id=robot_id,
            distance_km=current_waypoint["distance_km"],
            location=Location(**current_waypoint["location"]),
            battery=robot.get("battery", 100.0) - 0.1,
            speed=settings.ROBOT_SPEED,
            status="moving"
        )
        await self.update_robot_position(position)

        await inspection_robots_collection.update_one(
            {"robot_id": robot_id},
            {"$set": {"current_waypoint": current_waypoint_idx + 1}}
        )

    async def load_topology_map(self, map_id: str = "default") -> Optional[TopologyMap]:
        try:
            map_doc = await topology_map_collection.find_one({"map_id": map_id})
            if map_doc:
                self.topology_map = TopologyMap(**map_doc)
                logger.info(f"Loaded topology map: {map_id} with {len(self.topology_map.nodes)} nodes, {len(self.topology_map.edges)} edges")
                return self.topology_map
            
            logger.warning(f"Topology map {map_id} not found, creating default map")
            self.topology_map = await self._create_default_topology_map()
            return self.topology_map
        except Exception as e:
            logger.error(f"Error loading topology map: {e}")
            return None

    async def _create_default_topology_map(self) -> TopologyMap:
        nodes = []
        edges = []
        branch_points = []
        
        for i in range(0, int(settings.TUNNEL_LENGTH * 2) + 1):
            distance_km = i * 0.5
            node_id = f"node_{distance_km:.1f}"
            coords = await self._get_tunnel_coordinates(distance_km)
            
            node_type = "normal"
            connections = []
            
            if i > 0:
                connections.append(f"node_{(i-1)*0.5:.1f}")
            if i < int(settings.TUNNEL_LENGTH * 2):
                connections.append(f"node_{(i+1)*0.5:.1f}")
            
            if distance_km in [3.0, 6.0, 9.0, 12.0]:
                node_type = "branch"
                branch_points.append(node_id)
                for chamber in settings.CHAMBERS:
                    branch_node_id = f"branch_{distance_km:.1f}_{chamber}"
                    branch_coords = [coords[0] + 0.001 * settings.CHAMBERS.index(chamber), coords[1]]
                    branch_node = TopologyNode(
                        node_id=branch_node_id,
                        distance_km=distance_km,
                        chamber=chamber,
                        location=Location(coordinates=branch_coords),
                        node_type="branch_exit",
                        connections=[node_id]
                    )
                    nodes.append(branch_node)
                    connections.append(branch_node_id)
                    
                    edge = TopologyEdge(
                        edge_id=f"edge_{node_id}_{branch_node_id}",
                        from_node=node_id,
                        to_node=branch_node_id,
                        distance=0.1,
                        safety_score=0.9,
                        energy_cost=1.2,
                        time_cost=1.5
                    )
                    edges.append(edge)
            
            node = TopologyNode(
                node_id=node_id,
                distance_km=distance_km,
                chamber="main",
                location=Location(coordinates=coords),
                node_type=node_type,
                connections=connections
            )
            nodes.append(node)
            
            if i < int(settings.TUNNEL_LENGTH * 2):
                next_node_id = f"node_{(i+1)*0.5:.1f}"
                edge = TopologyEdge(
                    edge_id=f"edge_{node_id}_{next_node_id}",
                    from_node=node_id,
                    to_node=next_node_id,
                    distance=0.5,
                    safety_score=1.0,
                    energy_cost=1.0,
                    time_cost=1.0
                )
                edges.append(edge)
        
        topology_map = TopologyMap(
            map_id="default",
            name="Default Utility Tunnel Topology",
            nodes=nodes,
            edges=edges,
            branch_points=branch_points
        )
        
        await topology_map_collection.insert_one(topology_map.model_dump(exclude={"id"}))
        logger.info(f"Created default topology map with {len(nodes)} nodes, {len(edges)} edges, {len(branch_points)} branch points")
        return topology_map

    def _heuristic(self, node1: TopologyNode, node2: TopologyNode) -> float:
        return abs(node1.distance_km - node2.distance_km)

    async def _astar_path_planning(
        self,
        start_node_id: str,
        end_node_id: str,
        weight_override: Optional[Dict[str, float]] = None
    ) -> Tuple[List[str], float, float, float, float]:
        if not self.topology_map:
            raise ValueError("Topology map not loaded")
        
        weights = weight_override or settings.ROBOT_GLOBAL_PLANNING_WEIGHT
        
        node_map = {node.node_id: node for node in self.topology_map.nodes}
        edge_map = {}
        for edge in self.topology_map.edges:
            if edge.from_node not in edge_map:
                edge_map[edge.from_node] = []
            edge_map[edge.from_node].append(edge)
            if edge.to_node not in edge_map:
                edge_map[edge.to_node] = []
            reverse_edge = TopologyEdge(
                edge_id=f"rev_{edge.edge_id}",
                from_node=edge.to_node,
                to_node=edge.from_node,
                distance=edge.distance,
                safety_score=edge.safety_score,
                energy_cost=edge.energy_cost,
                time_cost=edge.time_cost
            )
            edge_map[edge.to_node].append(reverse_edge)
        
        if start_node_id not in node_map or end_node_id not in node_map:
            raise ValueError(f"Start or end node not found: {start_node_id} -> {end_node_id}")
        
        start_node = node_map[start_node_id]
        end_node = node_map[end_node_id]
        
        open_set = {start_node_id}
        came_from = {}
        g_score = {start_node_id: 0.0}
        f_score = {start_node_id: self._heuristic(start_node, end_node)}
        
        while open_set:
            current = min(open_set, key=lambda n: f_score.get(n, float('inf')))
            
            if current == end_node_id:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.insert(0, current)
                
                total_distance = 0.0
                total_energy = 0.0
                total_time = 0.0
                total_safety = 0.0
                
                for i in range(len(path) - 1):
                    from_id = path[i]
                    to_id = path[i + 1]
                    for edge in edge_map.get(from_id, []):
                        if edge.to_node == to_id:
                            total_distance += edge.distance
                            total_energy += edge.energy_cost * edge.distance
                            total_time += edge.time_cost * edge.distance
                            total_safety += edge.safety_score
                            break
                
                avg_safety = total_safety / max(len(path) - 1, 1) if len(path) > 1 else 1.0
                
                path_score = (
                    weights["distance"] * (1.0 / max(total_distance, 0.1)) +
                    weights["safety"] * avg_safety +
                    weights["energy"] * (1.0 / max(total_energy, 0.1)) +
                    weights["time"] * (1.0 / max(total_time, 0.1))
                )
                
                return path, total_distance, total_energy, total_time, avg_safety, path_score
            
            open_set.remove(current)
            
            for edge in edge_map.get(current, []):
                neighbor = edge.to_node
                if neighbor not in node_map:
                    continue
                
                edge_cost = (
                    weights["distance"] * edge.distance +
                    weights["safety"] * (1.0 - edge.safety_score) * edge.distance +
                    weights["energy"] * edge.energy_cost * edge.distance +
                    weights["time"] * edge.time_cost * edge.distance
                )
                
                tentative_g = g_score[current] + edge_cost
                
                if tentative_g < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self._heuristic(node_map[neighbor], end_node)
                    open_set.add(neighbor)
        
        raise ValueError(f"No path found from {start_node_id} to {end_node_id}")

    async def _evaluate_branch_stability(
        self,
        node_id: str,
        chamber: str,
        distance_km: float
    ) -> BranchStabilityResult:
        env_data = await self._get_environment_data(distance_km, chamber)
        
        sensor_scores = {}
        for sensor, value in env_data.items():
            if sensor in self.branch_sensor_weights:
                if sensor == "temperature":
                    score = 1.0 - min(1.0, abs(value - 25.0) / 30.0)
                elif sensor == "humidity":
                    score = 1.0 - min(1.0, abs(value - 50.0) / 50.0)
                elif sensor == "methane":
                    score = 1.0 - min(1.0, value / settings.ROBOT_AVOID_GAS_METHANE)
                elif sensor == "h2s":
                    score = 1.0 - min(1.0, value / settings.ROBOT_AVOID_GAS_H2S)
                elif sensor == "oxygen":
                    score = 1.0 - min(1.0, abs(value - 20.5) / 5.0)
                else:
                    score = 1.0
                sensor_scores[sensor] = max(0.0, min(1.0, score))
        
        stability_score = sum(
            sensor_scores[sensor] * self.branch_sensor_weights[sensor]
            for sensor in self.branch_sensor_weights
        )
        
        is_stable = stability_score >= settings.ROBOT_BRANCH_STABILITY_THRESHOLD
        
        return BranchStabilityResult(
            node_id=node_id,
            stability_score=stability_score,
            sensor_readings=env_data,
            sensor_weights=self.branch_sensor_weights,
            is_stable=is_stable,
            recommended_path=None if is_stable else "alternative_route"
        )

    async def plan_path_with_retry(
        self,
        robot_id: str,
        start_km: float,
        end_km: float,
        chamber: str,
        inspection_points: Optional[List[float]] = None
    ) -> PathPlanningResult:
        if not self.topology_map:
            await self.load_topology_map()
        
        start_node_id = f"node_{start_km:.1f}"
        end_node_id = f"node_{end_km:.1f}"
        
        fallback_waypoints = []
        if inspection_points is None:
            inspection_points = []
            current = start_km
            while current <= end_km:
                inspection_points.append(current)
                current += 0.5
        
        for attempt in range(1, settings.ROBOT_PATH_PLANNING_ATTEMPTS + 1):
            try:
                logger.info(f"Path planning attempt {attempt}/{settings.ROBOT_PATH_PLANNING_ATTEMPTS} for robot {robot_id}")
                
                weight_adjustments = [None]
                if attempt > 1:
                    weight_adjustments = [
                        {"distance": 0.5, "safety": 0.3, "energy": 0.1, "time": 0.1},
                        {"distance": 0.2, "safety": 0.6, "energy": 0.1, "time": 0.1}
                    ]
                
                for weights in weight_adjustments:
                    try:
                        path, total_distance, total_energy, total_time, safety_score, path_score = await self._astar_path_planning(
                            start_node_id, end_node_id, weights
                        )
                        
                        node_map = {node.node_id: node for node in self.topology_map.nodes}
                        waypoints = []
                        waypoint_id = 0
                        avoided_areas = []
                        
                        for i, node_id in enumerate(path):
                            node = node_map[node_id]
                            
                            if node.node_type == "branch":
                                stability_result = await self._evaluate_branch_stability(
                                    node_id, chamber, node.distance_km
                                )
                                
                                if not stability_result.is_stable:
                                    logger.warning(f"Branch point {node_id} unstable (score: {stability_result.stability_score:.2f}), finding alternative")
                                    avoided_areas.append({
                                        "node_id": node_id,
                                        "distance_km": node.distance_km,
                                        "reason": f"分支点不稳定，得分{stability_result.stability_score:.2f}",
                                        "stability_data": stability_result.dict()
                                    })
                                    
                                    for conn_id in node.connections:
                                        if conn_id in node_map and node_map[conn_id].node_type == "branch_exit":
                                            conn_stability = await self._evaluate_branch_stability(
                                                conn_id, node_map[conn_id].chamber, node.distance_km
                                            )
                                            if conn_stability.is_stable:
                                                stability_result.recommended_path = conn_id
                                                break
                            
                            if any(abs(ip - node.distance_km) < 0.05 for ip in inspection_points) or i == 0 or i == len(path) - 1:
                                waypoint = Waypoint(
                                    distance_km=node.distance_km,
                                    location=node.location,
                                    action="inspect",
                                    estimated_time=30.0,
                                    waypoint_id=waypoint_id
                                )
                                waypoints.append(waypoint)
                                waypoint_id += 1
                        
                        plan_id = f"path_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{robot_id}"
                        result = PathPlanningResult(
                            plan_id=plan_id,
                            robot_id=robot_id,
                            start_node=start_node_id,
                            end_node=end_node_id,
                            waypoints=waypoints,
                            total_distance=total_distance,
                            total_energy=total_energy,
                            total_time=total_time,
                            safety_score=safety_score,
                            path_score=path_score,
                            attempt_count=attempt,
                            status="success"
                        )
                        
                        await robot_path_plans_collection.insert_one(result.dict())
                        
                        mission_id = f"mission_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{robot_id}"
                        mission = InspectionMission(
                            mission_id=mission_id,
                            robot_id=robot_id,
                            name=f"巡检任务 - {chamber} {start_km:.1f}-{end_km:.1f}km",
                            waypoints=waypoints,
                            status="pending",
                            avoided_areas=avoided_areas,
                            priority=1
                        )
                        await inspection_missions_collection.insert_one(mission.model_dump(exclude={"id"}))
                        
                        logger.info(f"Path planning succeeded on attempt {attempt}, plan_id: {plan_id}")
                        return result
                        
                    except ValueError as e:
                        logger.warning(f"Path planning with weights {weights} failed: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Path planning attempt {attempt} failed: {e}")
                if attempt == settings.ROBOT_PATH_PLANNING_ATTEMPTS:
                    break
                await asyncio.sleep(1)
        
        logger.warning(f"All {settings.ROBOT_PATH_PLANNING_ATTEMPTS} path planning attempts failed, using fallback")
        fallback_mission = await self.plan_path(robot_id, start_km, end_km, chamber, inspection_points)
        
        fallback_waypoints = fallback_mission.waypoints
        plan_id = f"path_fallback_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{robot_id}"
        result = PathPlanningResult(
            plan_id=plan_id,
            robot_id=robot_id,
            start_node=start_node_id,
            end_node=end_node_id,
            waypoints=fallback_waypoints,
            total_distance=abs(end_km - start_km),
            total_energy=abs(end_km - start_km) * 2.0,
            total_time=abs(end_km - start_km) * 60.0,
            safety_score=0.5,
            path_score=0.3,
            attempt_count=settings.ROBOT_PATH_PLANNING_ATTEMPTS,
            status="fallback",
            fallback_reason="All A* path planning attempts failed"
        )
        
        await robot_path_plans_collection.insert_one(result.dict())
        return result


robot_inspector = RobotInspector()
