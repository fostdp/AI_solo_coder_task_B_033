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
    sensor_data_collection
)
from backend.models.schemas import (
    InspectionRobot,
    InspectionMission,
    Waypoint,
    RobotPosition,
    Location
)

logger = logging.getLogger(__name__)


class RobotInspector:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.running = False
        self.robot_tasks: Dict[str, asyncio.Task] = {}

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
        doc = position.model_dump()
        await robot_positions_collection.insert_one(doc)

        await inspection_robots_collection.update_one(
            {"robot_id": position.robot_id},
            {"$set": {
                "current_distance_km": position.distance_km,
                "location": position.location.model_dump(),
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
                    "location": position.location.model_dump(),
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


robot_inspector = RobotInspector()
