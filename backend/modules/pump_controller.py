import asyncio
import json
import logging
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from collections import deque

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from backend.config import settings
from backend.models.schemas import ControlCommand, DeviceType
from backend.models.database import (
    devices_collection,
    control_commands_collection,
    serialize_document
)
from backend.services.mqtt_service import mqtt_service

logger = logging.getLogger(__name__)


class PumpControllerModule:
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.running = False
        self.auto_mode: Dict[str, bool] = {}
        self.level_history: Dict[str, deque] = {}
        self.pump_states: Dict[str, Dict[str, Any]] = {}
        self.warning_timers: Dict[str, asyncio.Task] = {}
        self.min_run_time = 30
        self.warning_delay = 60
        self.level_high = 80.0
        self.level_low = 30.0
        self.level_warning = 90.0

    async def connect_redis(self):
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory mode")
            self.redis_client = None
            return

        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis connected successfully for pump controller")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}, using in-memory mode")
            self.redis_client = None

    async def disconnect_redis(self):
        for timer in self.warning_timers.values():
            if not timer.done():
                timer.cancel()
        self.warning_timers.clear()

        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.aclose()
            self.pubsub = None

        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    def _init_pump(self, pump_id: str):
        if pump_id not in self.pump_states:
            self.pump_states[pump_id] = {
                "running": False,
                "last_start_time": None,
                "last_stop_time": None,
                "start_count": 0,
                "run_duration": 0.0
            }
            self.level_history[pump_id] = deque(maxlen=10)
            self.auto_mode[pump_id] = True

    def _get_average_level(self, pump_id: str) -> float:
        history = self.level_history.get(pump_id, deque())
        if not history:
            return 0.0
        return sum(history) / len(history)

    def set_manual_mode(self, pump_id: str, running: bool):
        self._init_pump(pump_id)
        self.auto_mode[pump_id] = False

        if pump_id in self.warning_timers:
            if not self.warning_timers[pump_id].done():
                self.warning_timers[pump_id].cancel()
            del self.warning_timers[pump_id]

        state = self.pump_states[pump_id]
        current_time = datetime.utcnow()

        if running != state["running"]:
            if running:
                state["running"] = True
                state["last_start_time"] = current_time
                state["start_count"] += 1
            else:
                state["running"] = False
                state["last_stop_time"] = current_time
                if state["last_start_time"]:
                    duration = (current_time - state["last_start_time"]).total_seconds()
                    state["run_duration"] += duration

    def set_auto_mode(self, pump_id: str):
        self._init_pump(pump_id)
        self.auto_mode[pump_id] = True

    def get_pump_state(self, pump_id: str) -> Dict[str, Any]:
        self._init_pump(pump_id)
        return self.pump_states[pump_id].copy()

    def get_all_pump_states(self) -> Dict[str, Dict[str, Any]]:
        return {pid: state.copy() for pid, state in self.pump_states.items()}

    async def _publish_control_command(self, pump_id: str, running: bool, reason: str, level: float) -> Dict[str, Any]:
        command = ControlCommand(
            device_id=pump_id,
            command="start" if running else "stop",
            parameters={
                "running": running,
                "reason": reason,
                "level": level,
                "source": "automatic" if self.auto_mode.get(pump_id, True) else "manual"
            },
            source="automatic" if self.auto_mode.get(pump_id, True) else "manual"
        )

        command_dict = command.dict()
        command_dict["timestamp"] = command_dict["timestamp"].isoformat()

        if self.redis_client:
            try:
                await self.redis_client.publish(
                    settings.REDIS_CHANNEL_CONTROL_COMMAND,
                    json.dumps(command_dict)
                )
            except Exception as e:
                logger.error(f"Failed to publish control command to Redis: {e}")

        await control_commands_collection.insert_one(command.dict())

        await mqtt_service.publish_control_command(
            device_id=pump_id,
            command="start" if running else "stop",
            parameters=command.parameters
        )

        return command_dict

    async def _warning_timeout_handler(self, pump_id: str):
        try:
            await asyncio.sleep(self.warning_delay)
            self._init_pump(pump_id)
            state = self.pump_states[pump_id]

            if self.auto_mode.get(pump_id, True) and not state["running"]:
                avg_level = self._get_average_level(pump_id)
                if avg_level >= self.level_warning:
                    logger.warning(f"Pump {pump_id} warning timeout: level {avg_level:.1f}%, starting pump")
                    await self._execute_control(pump_id, True, "warning_timeout", avg_level)
        except asyncio.CancelledError:
            logger.info(f"Warning timer cancelled for pump {pump_id}")
        except Exception as e:
            logger.error(f"Error in warning timeout handler for pump {pump_id}: {e}")

    async def _execute_control(self, pump_id: str, should_run: bool, reason: str, level: float):
        state = self.pump_states[pump_id]
        current_time = datetime.utcnow()

        if should_run:
            state["running"] = True
            state["last_start_time"] = current_time
            state["start_count"] += 1
            logger.info(f"Pump {pump_id} started - level: {level:.1f}%, reason: {reason}")
        else:
            state["running"] = False
            state["last_stop_time"] = current_time
            if state["last_start_time"]:
                duration = (current_time - state["last_start_time"]).total_seconds()
                state["run_duration"] += duration
            logger.info(f"Pump {pump_id} stopped - level: {level:.1f}%, reason: {reason}")

        await self._publish_control_command(pump_id, should_run, reason, level)

    def calculate_control(self, pump_id: str, level: float) -> Tuple[Optional[bool], str, float]:
        self._init_pump(pump_id)

        self.level_history[pump_id].append(level)
        avg_level = self._get_average_level(pump_id)

        if not self.auto_mode.get(pump_id, True):
            return None, "manual_mode", avg_level

        state = self.pump_states[pump_id]
        current_time = datetime.utcnow()

        if state["running"]:
            if avg_level <= self.level_low:
                if state["last_start_time"]:
                    run_duration = (current_time - state["last_start_time"]).total_seconds()
                    if run_duration >= self.min_run_time:
                        return False, "level_normal", avg_level
                    else:
                        return None, f"min_run_time_{int(self.min_run_time - run_duration)}s_remaining", avg_level
                else:
                    return False, "level_normal", avg_level
            else:
                return None, "pumping", avg_level
        else:
            if avg_level >= self.level_high:
                if pump_id in self.warning_timers:
                    if not self.warning_timers[pump_id].done():
                        self.warning_timers[pump_id].cancel()
                    del self.warning_timers[pump_id]
                return True, "level_high", avg_level
            elif avg_level >= self.level_warning:
                if pump_id not in self.warning_timers or self.warning_timers[pump_id].done():
                    self.warning_timers[pump_id] = asyncio.create_task(
                        self._warning_timeout_handler(pump_id)
                    )
                    logger.warning(f"Pump {pump_id} level {avg_level:.1f}% >= {self.level_warning}%, starting {self.warning_delay}s warning timer")
                return None, "warning_delay", avg_level
            else:
                if pump_id in self.warning_timers:
                    if not self.warning_timers[pump_id].done():
                        self.warning_timers[pump_id].cancel()
                    del self.warning_timers[pump_id]
                return None, "normal", avg_level

    async def process_sensor_data(self, message: Dict[str, Any]):
        try:
            device_id = message.get("device_id")
            device_type = message.get("type", message.get("device_info", {}).get("type"))

            if device_type != DeviceType.PUMP:
                return

            data = message.get("data", {})
            level = data.get("level")

            if level is None:
                return

            should_control, reason, avg_level = self.calculate_control(device_id, level)

            if should_control is not None:
                await self._execute_control(device_id, should_control, reason, avg_level)

            await devices_collection.update_one(
                {"device_id": device_id},
                {
                    "$set": {
                        "properties.pump_state": self.get_pump_state(device_id),
                        "properties.current_level": level,
                        "properties.average_level": round(avg_level, 2),
                        "properties.control_reason": reason,
                        "properties.auto_mode": self.auto_mode.get(device_id, True)
                    }
                }
            )

        except Exception as e:
            logger.error(f"Error processing sensor data for pump control: {e}")

    async def _redis_subscriber(self):
        if not self.redis_client:
            logger.warning("Redis not available, cannot subscribe to sensor data")
            return

        try:
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(settings.REDIS_CHANNEL_SENSOR_DATA)

            logger.info(f"Subscribed to Redis channel: {settings.REDIS_CHANNEL_SENSOR_DATA}")

            async for message in self.pubsub.listen():
                if not self.running:
                    break

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self.process_sensor_data(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse Redis message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")

        except Exception as e:
            logger.error(f"Redis subscriber error: {e}")
        finally:
            if self.pubsub:
                try:
                    await self.pubsub.unsubscribe()
                    await self.pubsub.aclose()
                except Exception:
                    pass
                self.pubsub = None

    async def start(self):
        if self.running:
            logger.warning("Pump controller module is already running")
            return

        await self.connect_redis()
        self.running = True

        asyncio.create_task(self._redis_subscriber())
        logger.info("Pump controller module started")

    async def stop(self):
        self.running = False

        for timer in self.warning_timers.values():
            if not timer.done():
                timer.cancel()
        self.warning_timers.clear()

        await self.disconnect_redis()
        logger.info("Pump controller module stopped")
    
    async def start_control_loop(self):
        await self.start()
    
    async def stop_control_loop(self):
        await self.stop()


pump_controller = PumpControllerModule()
