import multiprocessing
import multiprocessing.queues
import time
import logging
import math
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

_request_queue: Optional[multiprocessing.Queue] = None
_response_queue: Optional[multiprocessing.Queue] = None
_process: Optional[multiprocessing.Process] = None
_process_start_time: Optional[float] = None
_requests_processed: int = 0
_total_response_time_ms: float = 0.0


class _TopologyNode:
    def __init__(self, node_data: Dict[str, Any]):
        self.node_id = node_data["node_id"]
        self.distance_km = node_data["distance_km"]
        self.chamber = node_data.get("chamber", "main")
        self.location = node_data.get("location", {})
        self.node_type = node_data.get("node_type", "normal")
        self.connections = node_data.get("connections", [])


class _TopologyEdge:
    def __init__(self, edge_data: Dict[str, Any]):
        self.edge_id = edge_data["edge_id"]
        self.from_node = edge_data["from_node"]
        self.to_node = edge_data["to_node"]
        self.distance = edge_data["distance"]
        self.safety_score = edge_data["safety_score"]
        self.energy_cost = edge_data["energy_cost"]
        self.time_cost = edge_data["time_cost"]


def _heuristic(node1: _TopologyNode, node2: _TopologyNode) -> float:
    return abs(node1.distance_km - node2.distance_km)


def _astar_path_planning(
    start_node_id: str,
    end_node_id: str,
    nodes_data: List[Dict[str, Any]],
    edges_data: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None
) -> Tuple[List[str], float, float, float, float, float]:
    if weights is None:
        weights = {"distance": 0.3, "safety": 0.4, "energy": 0.15, "time": 0.15}

    node_map = {node_data["node_id"]: _TopologyNode(node_data) for node_data in nodes_data}
    edge_map: Dict[str, List[_TopologyEdge]] = {}

    for edge_data in edges_data:
        edge = _TopologyEdge(edge_data)
        if edge.from_node not in edge_map:
            edge_map[edge.from_node] = []
        edge_map[edge.from_node].append(edge)
        if edge.to_node not in edge_map:
            edge_map[edge.to_node] = []
        reverse_edge = _TopologyEdge({
            "edge_id": f"rev_{edge.edge_id}",
            "from_node": edge.to_node,
            "to_node": edge.from_node,
            "distance": edge.distance,
            "safety_score": edge.safety_score,
            "energy_cost": edge.energy_cost,
            "time_cost": edge.time_cost
        })
        edge_map[edge.to_node].append(reverse_edge)

    if start_node_id not in node_map or end_node_id not in node_map:
        raise ValueError(f"Start or end node not found: {start_node_id} -> {end_node_id}")

    start_node = node_map[start_node_id]
    end_node = node_map[end_node_id]

    open_set = {start_node_id}
    came_from: Dict[str, str] = {}
    g_score: Dict[str, float] = {start_node_id: 0.0}
    f_score: Dict[str, float] = {start_node_id: _heuristic(start_node, end_node)}

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
                f_score[neighbor] = tentative_g + _heuristic(node_map[neighbor], end_node)
                open_set.add(neighbor)

    raise ValueError(f"No path found from {start_node_id} to {end_node_id}")


def _path_planner_worker(
    request_queue: multiprocessing.Queue,
    response_queue: multiprocessing.Queue
):
    logger.info("Path planner process started")

    while True:
        try:
            request = request_queue.get(timeout=None)

            if request is None:
                logger.info("Path planner process received shutdown signal")
                break

            start_time = time.time()
            request_id = request.get("request_id")
            response = {
                "request_id": request_id,
                "success": False,
                "error": None
            }

            try:
                topology_map_data = request.get("topology_map_data")
                if not topology_map_data:
                    raise ValueError("No topology map data provided")

                start_km = request["start_km"]
                end_km = request["end_km"]
                start_node_id = f"node_{start_km:.1f}"
                end_node_id = f"node_{end_km:.1f}"

                weights = request.get("weight_override")
                nodes_data = topology_map_data.get("nodes", [])
                edges_data = topology_map_data.get("edges", [])

                path, total_distance, total_energy, total_time, safety_score, path_score = _astar_path_planning(
                    start_node_id, end_node_id, nodes_data, edges_data, weights
                )

                response.update({
                    "success": True,
                    "path": path,
                    "total_distance": total_distance,
                    "total_energy": total_energy,
                    "total_time": total_time,
                    "safety_score": safety_score,
                    "path_score": path_score
                })

            except Exception as e:
                logger.error(f"Path planning error: {e}")
                response["error"] = str(e)

            finally:
                processing_time_ms = (time.time() - start_time) * 1000
                response["processing_time_ms"] = processing_time_ms
                response_queue.put(response)

        except Exception as e:
            logger.error(f"Path planner worker error: {e}")
            time.sleep(0.1)

    logger.info("Path planner process stopped")


def start_path_planner_process() -> bool:
    global _request_queue, _response_queue, _process, _process_start_time, _requests_processed, _total_response_time_ms

    if _process and _process.is_alive():
        logger.warning("Path planner process is already running")
        return True

    try:
        _request_queue = multiprocessing.Queue(maxsize=100)
        _response_queue = multiprocessing.Queue(maxsize=100)

        _process = multiprocessing.Process(
            target=_path_planner_worker,
            args=(_request_queue, _response_queue),
            daemon=True,
            name="path-planner-process"
        )

        _process.start()
        _process_start_time = time.time()
        _requests_processed = 0
        _total_response_time_ms = 0.0

        logger.info(f"Path planner process started with PID {_process.pid}")
        return True

    except Exception as e:
        logger.error(f"Failed to start path planner process: {e}")
        _request_queue = None
        _response_queue = None
        _process = None
        return False


def stop_path_planner_process() -> bool:
    global _request_queue, _response_queue, _process, _process_start_time, _requests_processed, _total_response_time_ms

    success = True

    if _process and _process.is_alive():
        try:
            if _request_queue:
                _request_queue.put(None)

            _process.join(timeout=5)

            if _process.is_alive():
                logger.warning("Path planner process did not exit gracefully, terminating")
                _process.terminate()
                _process.join(timeout=2)

            logger.info("Path planner process stopped")
        except Exception as e:
            logger.error(f"Error stopping path planner process: {e}")
            success = False

    _request_queue = None
    _response_queue = None
    _process = None
    _process_start_time = None
    _requests_processed = 0
    _total_response_time_ms = 0.0

    return success


def is_process_running() -> bool:
    return _process is not None and _process.is_alive()


def send_path_planning_request(
    request_data: Dict[str, Any],
    timeout: float = 30.0
) -> Optional[Dict[str, Any]]:
    global _requests_processed, _total_response_time_ms

    if not is_process_running():
        raise RuntimeError("Path planner process is not running")

    if _request_queue is None or _response_queue is None:
        raise RuntimeError("Path planner queues not initialized")

    try:
        _request_queue.put(request_data, timeout=5)

        response = _response_queue.get(timeout=timeout)

        _requests_processed += 1
        if "processing_time_ms" in response:
            _total_response_time_ms += response["processing_time_ms"]

        return response

    except Exception as e:
        logger.error(f"Error sending path planning request: {e}")
        return None


def get_process_status() -> Dict[str, Any]:
    status = {
        "status": "stopped",
        "pid": None,
        "uptime_seconds": None,
        "requests_processed": None,
        "average_response_time_ms": None
    }

    if is_process_running() and _process:
        status["status"] = "running"
        status["pid"] = _process.pid

        if _process_start_time:
            status["uptime_seconds"] = time.time() - _process_start_time

        status["requests_processed"] = _requests_processed

        if _requests_processed > 0:
            status["average_response_time_ms"] = _total_response_time_ms / _requests_processed

    return status
