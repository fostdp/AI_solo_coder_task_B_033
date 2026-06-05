import time
import asyncio
from typing import Tuple, Dict, List, Optional
from config.settings import settings
from models.models import CabinType, OperationHistory
from utils.mqtt_client import mqtt_client
from config.database import get_collection


class CabinVentilationController:
    def __init__(self, cabin: CabinType):
        self.cabin = cabin
        self.oxygen_target = (settings.OXYGEN_MIN + settings.OXYGEN_MAX) / 2
        self.temp_max = settings.TEMP_MAX
        self.fan_states: Dict[str, dict] = {}
        self.last_inference_time: float = 0
        self.throttle_interval: float = 5.0
        self.cached_result: Optional[Tuple[bool, int]] = None
        self.pid_integral: float = 0.0
        self.pid_prev_error: float = 0.0
        self.pid_prev_time: float = time.time()
        self.sensor_readings: List[dict] = []
        self.max_readings: int = 10
        self.fan_device_ids: List[str] = []
        self._initialized: bool = False

    async def _init_fan_devices(self):
        if self._initialized:
            return
        try:
            fans = await get_collection("devices").find({
                "type": "fan",
                "cabin": self.cabin.value
            }).to_list(length=20)
            self.fan_device_ids = [f["device_id"] for f in fans]
            self._initialized = True
        except Exception as e:
            print(f"[通风控制 {self.cabin.value}] 初始化风机列表失败: {e}")

    def _fuzzify_oxygen(self, oxygen: float) -> str:
        if oxygen < 17.0:
            return "very_low"
        elif oxygen < 18.5:
            return "low"
        elif oxygen < 19.5:
            return "slightly_low"
        elif oxygen <= 21.0:
            return "normal"
        else:
            return "high"

    def _fuzzify_temperature(self, temp: float) -> str:
        if temp < 25:
            return "low"
        elif temp < 30:
            return "medium"
        elif temp < 35:
            return "high"
        else:
            return "very_high"

    def _fuzzify_humidity(self, humidity: float) -> str:
        if humidity < 40:
            return "low"
        elif humidity < 60:
            return "normal"
        elif humidity < 80:
            return "high"
        else:
            return "very_high"

    def _infer(self, oxy_level: str, temp_level: str, hum_level: str) -> Tuple[bool, int]:
        rule_table = {
            ("very_low", "very_high", "very_high"): (True, 100),
            ("very_low", "very_high", "high"): (True, 100),
            ("very_low", "very_high", "normal"): (True, 90),
            ("very_low", "very_high", "low"): (True, 85),
            ("very_low", "high", "very_high"): (True, 95),
            ("very_low", "high", "high"): (True, 90),
            ("very_low", "high", "normal"): (True, 85),
            ("very_low", "high", "low"): (True, 80),
            ("very_low", "medium", "very_high"): (True, 80),
            ("very_low", "medium", "high"): (True, 75),
            ("very_low", "medium", "normal"): (True, 70),
            ("very_low", "medium", "low"): (True, 65),
            ("very_low", "low", "very_high"): (True, 70),
            ("very_low", "low", "high"): (True, 65),
            ("very_low", "low", "normal"): (True, 60),
            ("very_low", "low", "low"): (True, 55),
            ("low", "very_high", "very_high"): (True, 90),
            ("low", "very_high", "high"): (True, 85),
            ("low", "very_high", "normal"): (True, 80),
            ("low", "very_high", "low"): (True, 75),
            ("low", "high", "very_high"): (True, 85),
            ("low", "high", "high"): (True, 80),
            ("low", "high", "normal"): (True, 75),
            ("low", "high", "low"): (True, 70),
            ("low", "medium", "very_high"): (True, 70),
            ("low", "medium", "high"): (True, 65),
            ("low", "medium", "normal"): (True, 60),
            ("low", "medium", "low"): (True, 55),
            ("low", "low", "very_high"): (True, 60),
            ("low", "low", "high"): (True, 55),
            ("low", "low", "normal"): (True, 50),
            ("low", "low", "low"): (False, 0),
            ("slightly_low", "very_high", "very_high"): (True, 75),
            ("slightly_low", "very_high", "high"): (True, 70),
            ("slightly_low", "very_high", "normal"): (True, 65),
            ("slightly_low", "very_high", "low"): (True, 60),
            ("slightly_low", "high", "very_high"): (True, 70),
            ("slightly_low", "high", "high"): (True, 65),
            ("slightly_low", "high", "normal"): (True, 60),
            ("slightly_low", "high", "low"): (True, 55),
            ("slightly_low", "medium", "very_high"): (True, 55),
            ("slightly_low", "medium", "high"): (True, 50),
            ("slightly_low", "medium", "normal"): (False, 0),
            ("slightly_low", "medium", "low"): (False, 0),
            ("slightly_low", "low", "very_high"): (True, 50),
            ("slightly_low", "low", "high"): (False, 0),
            ("slightly_low", "low", "normal"): (False, 0),
            ("slightly_low", "low", "low"): (False, 0),
            ("normal", "very_high", "very_high"): (True, 60),
            ("normal", "very_high", "high"): (True, 55),
            ("normal", "very_high", "normal"): (True, 50),
            ("normal", "very_high", "low"): (False, 0),
            ("normal", "high", "very_high"): (True, 55),
            ("normal", "high", "high"): (True, 50),
            ("normal", "high", "normal"): (False, 0),
            ("normal", "high", "low"): (False, 0),
            ("normal", "medium", "very_high"): (False, 0),
            ("normal", "medium", "high"): (False, 0),
            ("normal", "medium", "normal"): (False, 0),
            ("normal", "medium", "low"): (False, 0),
            ("normal", "low", "very_high"): (False, 0),
            ("normal", "low", "high"): (False, 0),
            ("normal", "low", "normal"): (False, 0),
            ("normal", "low", "low"): (False, 0),
            ("high", "very_high", "very_high"): (True, 40),
            ("high", "very_high", "high"): (True, 35),
            ("high", "very_high", "normal"): (True, 30),
            ("high", "very_high", "low"): (False, 0),
            ("high", "high", "very_high"): (True, 30),
            ("high", "high", "high"): (False, 0),
            ("high", "high", "normal"): (False, 0),
            ("high", "high", "low"): (False, 0),
        }

        key = (oxy_level, temp_level, hum_level)
        if key in rule_table:
            return rule_table[key]

        if temp_level in ["very_high", "high"]:
            return (True, 40)
        return (False, 0)

    def _calculate_fuzzy(self, oxygen: float, temperature: float, humidity: float) -> Tuple[bool, int]:
        oxy_level = self._fuzzify_oxygen(oxygen)
        temp_level = self._fuzzify_temperature(temperature)
        hum_level = self._fuzzify_humidity(humidity)
        return self._infer(oxy_level, temp_level, hum_level)

    def _add_reading(self, oxygen: float, temperature: float, humidity: float):
        self.sensor_readings.append({
            "oxygen": oxygen,
            "temperature": temperature,
            "humidity": humidity,
            "time": time.time()
        })
        if len(self.sensor_readings) > self.max_readings:
            self.sensor_readings.pop(0)

    def _get_average_readings(self) -> Tuple[float, float, float]:
        if not self.sensor_readings:
            return (20.0, 25.0, 50.0)
        count = len(self.sensor_readings)
        avg_oxy = sum(r["oxygen"] for r in self.sensor_readings) / count
        avg_temp = sum(r["temperature"] for r in self.sensor_readings) / count
        avg_hum = sum(r["humidity"] for r in self.sensor_readings) / count
        return (avg_oxy, avg_temp, avg_hum)

    async def process_sensor_data(self, oxygen: float, temperature: float, humidity: float) -> Optional[Tuple[bool, int]]:
        await self._init_fan_devices()

        self._add_reading(oxygen, temperature, humidity)

        now = time.time()
        if now - self.last_inference_time < self.throttle_interval:
            return self.cached_result

        avg_oxy, avg_temp, avg_hum = self._get_average_readings()

        start_time = time.time()
        should_run, speed = self._calculate_fuzzy(avg_oxy, avg_temp, avg_hum)
        inference_time = (time.time() - start_time) * 1000

        self.last_inference_time = now
        self.cached_result = (should_run, speed)

        asyncio.create_task(self._apply_control(should_run, speed, avg_oxy, avg_temp, avg_hum))

        print(f"[通风控制 {self.cabin.value}] 推理完成: 运行={should_run}, 转速={speed}%, 耗时={inference_time:.2f}ms, 风机数={len(self.fan_device_ids)}")

        return (should_run, speed)

    async def _apply_control(self, should_run: bool, speed: int, oxygen: float, temperature: float, humidity: float):
        try:
            op_histories = []
            for device_id in self.fan_device_ids:
                current_state = self.get_fan_state(device_id)
                if should_run != current_state["is_running"] or abs(speed - current_state.get("speed", 0)) > 10:
                    command = "start" if should_run else "stop"
                    mqtt_client.send_fan_command(device_id, command, speed if should_run else 0)
                    self.update_fan_state(device_id, should_run, speed if should_run else 0)

                    op_histories.append(OperationHistory(
                        device_id=device_id,
                        operation=f"fan_auto_{command}",
                        operator="ventilation_system",
                        parameters={
                            "speed": speed if should_run else 0,
                            "reason": "environmental_control",
                            "oxygen": oxygen,
                            "temperature": temperature,
                            "humidity": humidity,
                            "cabin": self.cabin.value
                        }
                    ).dict())

            if op_histories:
                await get_collection("operation_history").insert_many(op_histories)
                print(f"[通风控制 {self.cabin.value}] 已向 {len(op_histories)} 台风机发送控制指令")

        except Exception as e:
            print(f"[通风控制 {self.cabin.value}] 应用控制指令失败: {e}")

    def update_fan_state(self, device_id: str, is_running: bool, speed: int):
        self.fan_states[device_id] = {
            "is_running": is_running,
            "speed": speed,
            "last_update": time.time()
        }

    def get_fan_state(self, device_id: str) -> dict:
        return self.fan_states.get(device_id, {"is_running": False, "speed": 0})


class VentilationControllerManager:
    def __init__(self):
        self.cabin_controllers: Dict[str, CabinVentilationController] = {
            CabinType.POWER.value: CabinVentilationController(CabinType.POWER),
            CabinType.WATER.value: CabinVentilationController(CabinType.WATER),
            CabinType.GAS.value: CabinVentilationController(CabinType.GAS),
        }

    def get_controller(self, cabin: CabinType) -> CabinVentilationController:
        return self.cabin_controllers[cabin.value]

    async def process_sensor_data(self, cabin: CabinType, oxygen: float, temperature: float, humidity: float):
        controller = self.get_controller(cabin)
        return await controller.process_sensor_data(oxygen, temperature, humidity)

    def update_fan_state(self, device_id: str, cabin: CabinType, is_running: bool, speed: int):
        controller = self.get_controller(cabin)
        controller.update_fan_state(device_id, is_running, speed)

    def get_fan_state(self, device_id: str, cabin: CabinType) -> dict:
        controller = self.get_controller(cabin)
        return controller.get_fan_state(device_id)


ventilation_controller = VentilationControllerManager()

