import time
import asyncio
from typing import Dict, Optional
from config.settings import settings
from models.models import OperationHistory, CabinType
from utils.mqtt_client import mqtt_client
from utils.redis_client import redis_client, RedisChannels
from config.database import get_collection


class PumpController:
    def __init__(self):
        self.start_level = settings.PUMP_START_LEVEL
        self.stop_level = settings.PUMP_STOP_LEVEL
        self.delay_seconds = settings.PUMP_DELAY
        self.pump_states: Dict[str, dict] = {}
        self.stop_timers: Dict[str, asyncio.Task] = {}
        self._subscribed: bool = False

    def get_pump_state(self, device_id: str) -> dict:
        if device_id not in self.pump_states:
            self.pump_states[device_id] = {
                "is_running": False,
                "current_level": 0.0,
                "last_start_time": None,
                "last_stop_time": None,
                "start_count": 0,
                "stop_count": 0,
                "cabin": None
            }
        return self.pump_states[device_id]

    async def _delayed_stop(self, device_id: str, cabin: str):
        try:
            await asyncio.sleep(self.delay_seconds)
            state = self.get_pump_state(device_id)
            if state["current_level"] <= self.stop_level and state["is_running"]:
                mqtt_client.send_pump_command(device_id, "stop")
                state["is_running"] = False
                state["last_stop_time"] = time.time()
                state["stop_count"] += 1

                op_history = OperationHistory(
                    device_id=device_id,
                    operation="pump_auto_stop",
                    operator="system",
                    parameters={"reason": "level_below_threshold", "level": state["current_level"]}
                )
                await get_collection("operation_history").insert_one(op_history.dict())

                await redis_client.publish(RedisChannels.DEVICE_UPDATE, {
                    "device_id": device_id,
                    "type": "pump",
                    "status": "normal",
                    "data": {
                        "is_running": False,
                        "level": state["current_level"]
                    },
                    "cabin": cabin
                })

                print(f"[排水控制] 水泵 {device_id} 延时停止完成，当前液位: {state['current_level']:.2f}m")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[排水控制] 延时停止错误: {e}")

    async def process_level_data(self, device_id: str, cabin: str, level: float, is_running: bool):
        state = self.get_pump_state(device_id)
        state["current_level"] = level
        state["is_running"] = is_running
        state["cabin"] = cabin

        if device_id in self.stop_timers and not self.stop_timers[device_id].done():
            if level > self.stop_level:
                self.stop_timers[device_id].cancel()
                print(f"[排水控制] 取消水泵 {device_id} 停止延时，液位回升: {level:.2f}m")
            return

        if level >= self.start_level and not is_running:
            mqtt_client.send_pump_command(device_id, "start")
            state["is_running"] = True
            state["last_start_time"] = time.time()
            state["start_count"] += 1

            op_history = OperationHistory(
                device_id=device_id,
                operation="pump_auto_start",
                operator="system",
                parameters={"reason": "level_exceeded", "level": level}
            )
            await get_collection("operation_history").insert_one(op_history.dict())

            await redis_client.publish(RedisChannels.DEVICE_UPDATE, {
                "device_id": device_id,
                "type": "pump",
                "status": "normal",
                "data": {
                    "is_running": True,
                    "level": level
                },
                "cabin": cabin
            })

            print(f"[排水控制] 水泵 {device_id} 自动启动，液位: {level:.2f}m")

        elif level <= self.stop_level and is_running:
            if device_id in self.stop_timers and not self.stop_timers[device_id].done():
                return
            self.stop_timers[device_id] = asyncio.create_task(self._delayed_stop(device_id, cabin))
            print(f"[排水控制] 水泵 {device_id} 将在 {self.delay_seconds}s 后停止，当前液位: {level:.2f}m")

    async def process_pump_telemetry(self, data: dict):
        try:
            device_id = data.get('device_id')
            cabin = data.get('cabin', 'water')
            level = data.get('level', 0.0)
            is_running = data.get('is_running', False)

            if device_id and level is not None:
                await self.process_level_data(device_id, cabin, level, is_running)
        except Exception as e:
            print(f"[排水控制] 处理遥测数据失败: {e}")

    async def _handle_pump_data(self, data: dict):
        try:
            device_id = data.get('device_id')
            cabin = data.get('cabin')
            level = data.get('level')
            is_running = data.get('is_running', False)

            if device_id and level is not None:
                cabin_value = cabin.value if isinstance(cabin, CabinType) else cabin
                await self.process_level_data(device_id, cabin_value or 'water', level, is_running)
        except Exception as e:
            print(f"[排水控制] 处理Redis消息失败: {e}")

    async def start_subscription(self):
        if self._subscribed:
            return
        try:
            await redis_client.subscribe(RedisChannels.PUMP_DATA, self._handle_pump_data)
            self._subscribed = True
            print("[排水控制] Redis订阅已启动")
        except Exception as e:
            print(f"[排水控制] Redis订阅失败: {e}")

    def manual_control(self, device_id: str, command: str, operator: str = "manual"):
        if command == "start":
            mqtt_client.send_pump_command(device_id, "start")
            state = self.get_pump_state(device_id)
            state["is_running"] = True
        elif command == "stop":
            if device_id in self.stop_timers and not self.stop_timers[device_id].done():
                self.stop_timers[device_id].cancel()
            mqtt_client.send_pump_command(device_id, "stop")
            state = self.get_pump_state(device_id)
            state["is_running"] = False


pump_controller = PumpController()
