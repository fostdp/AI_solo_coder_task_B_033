import os
import time
import yaml
import asyncio
from typing import Tuple, Dict, List, Optional
from config.settings import settings
from models.models import CabinType, OperationHistory
from utils.mqtt_client import mqtt_client
from utils.redis_client import redis_client, RedisChannels
from config.database import get_collection


class FuzzyConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: dict = {}
        self.rule_table: Dict[Tuple[str, str, str], Tuple[bool, int]] = {}
        self.thresholds: Dict[str, Dict[str, float]] = {}
        self.control_params: dict = {}
        self._load_config()

    def _load_config(self):
        if not os.path.exists(self.config_path):
            print(f"[模糊配置] 配置文件不存在: {self.config_path}，使用默认配置")
            self._load_default_config()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)

            fuzzy_logic = self.config.get('fuzzy_logic', {})

            input_vars = fuzzy_logic.get('input_variables', {})
            for var_name, var_config in input_vars.items():
                self.thresholds[var_name] = var_config.get('crisp_thresholds', {})

            rule_base = fuzzy_logic.get('rule_base', {})
            rules = rule_base.get('rules', [])
            for rule in rules:
                conditions = rule['conditions']
                key = (
                    conditions['oxygen'],
                    conditions['temperature'],
                    conditions['humidity']
                )
                output = rule['output']
                self.rule_table[key] = (output['should_run'], output['speed'])

            self.control_params = fuzzy_logic.get('control_parameters', {
                'throttle_interval': 5.0,
                'max_readings': 10,
                'speed_change_threshold': 10
            })

            print(f"[模糊配置] 已加载 {len(self.rule_table)} 条规则")
            print(f"[模糊配置] 控制参数: {self.control_params}")

        except Exception as e:
            print(f"[模糊配置] 加载失败: {e}，使用默认配置")
            self._load_default_config()

    def _load_default_config(self):
        self.thresholds = {
            'oxygen': {
                'very_low': 17.0,
                'low': 18.5,
                'slightly_low': 19.5,
                'normal': 21.0,
                'high': 21.0
            },
            'temperature': {
                'low': 25.0,
                'medium': 30.0,
                'high': 35.0,
                'very_high': 35.0
            },
            'humidity': {
                'low': 40.0,
                'normal': 60.0,
                'high': 80.0,
                'very_high': 80.0
            }
        }

        self.rule_table = {}
        default_rules = [
            (('very_low', 'very_high', 'very_high'), (True, 100)),
            (('very_low', 'very_high', 'high'), (True, 100)),
            (('very_low', 'very_high', 'normal'), (True, 90)),
            (('very_low', 'very_high', 'low'), (True, 85)),
            (('very_low', 'high', 'very_high'), (True, 95)),
            (('very_low', 'high', 'high'), (True, 90)),
            (('very_low', 'high', 'normal'), (True, 85)),
            (('very_low', 'high', 'low'), (True, 80)),
            (('low', 'low', 'low'), (False, 0)),
            (('normal', 'medium', 'normal'), (False, 0)),
            (('normal', 'low', 'low'), (False, 0)),
        ]
        for key, value in default_rules:
            self.rule_table[key] = value

        self.control_params = {
            'throttle_interval': 5.0,
            'max_readings': 10,
            'speed_change_threshold': 10
        }
        print(f"[模糊配置] 使用默认配置，{len(self.rule_table)} 条规则")


class CabinVentilationController:
    def __init__(self, cabin: CabinType, fuzzy_config: FuzzyConfigLoader):
        self.cabin = cabin
        self.fuzzy_config = fuzzy_config
        self.oxygen_target = (settings.OXYGEN_MIN + settings.OXYGEN_MAX) / 2
        self.temp_max = settings.TEMP_MAX
        self.fan_states: Dict[str, dict] = {}
        self.last_inference_time: float = 0
        self.throttle_interval: float = fuzzy_config.control_params.get('throttle_interval', 5.0)
        self.cached_result: Optional[Tuple[bool, int]] = None
        self.sensor_readings: List[dict] = []
        self.max_readings: int = fuzzy_config.control_params.get('max_readings', 10)
        self.speed_change_threshold: int = fuzzy_config.control_params.get('speed_change_threshold', 10)
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
            print(f"[通风控制 {self.cabin.value}] 初始化风机列表完成，共 {len(self.fan_device_ids)} 台")
        except Exception as e:
            print(f"[通风控制 {self.cabin.value}] 初始化风机列表失败: {e}")

    def _fuzzify_oxygen(self, oxygen: float) -> str:
        thresholds = self.fuzzy_config.thresholds.get('oxygen', {})
        if oxygen < thresholds.get('very_low', 17.0):
            return "very_low"
        elif oxygen < thresholds.get('low', 18.5):
            return "low"
        elif oxygen < thresholds.get('slightly_low', 19.5):
            return "slightly_low"
        elif oxygen <= thresholds.get('normal', 21.0):
            return "normal"
        else:
            return "high"

    def _fuzzify_temperature(self, temp: float) -> str:
        thresholds = self.fuzzy_config.thresholds.get('temperature', {})
        if temp < thresholds.get('low', 25.0):
            return "low"
        elif temp < thresholds.get('medium', 30.0):
            return "medium"
        elif temp < thresholds.get('high', 35.0):
            return "high"
        else:
            return "very_high"

    def _fuzzify_humidity(self, humidity: float) -> str:
        thresholds = self.fuzzy_config.thresholds.get('humidity', {})
        if humidity < thresholds.get('low', 40.0):
            return "low"
        elif humidity < thresholds.get('normal', 60.0):
            return "normal"
        elif humidity < thresholds.get('high', 80.0):
            return "high"
        else:
            return "very_high"

    def _infer(self, oxy_level: str, temp_level: str, hum_level: str) -> Tuple[bool, int]:
        key = (oxy_level, temp_level, hum_level)
        if key in self.fuzzy_config.rule_table:
            return self.fuzzy_config.rule_table[key]

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
                current_speed = current_state.get("speed", 0)
                speed_diff = abs(speed - current_speed) if should_run else current_speed

                if should_run != current_state["is_running"] or speed_diff > self.speed_change_threshold:
                    command = "start" if should_run else "stop"
                    actual_speed = speed if should_run else 0
                    mqtt_client.send_fan_command(device_id, command, actual_speed)
                    self.update_fan_state(device_id, should_run, actual_speed)

                    op_histories.append(OperationHistory(
                        device_id=device_id,
                        operation=f"fan_auto_{command}",
                        operator="ventilation_system",
                        parameters={
                            "speed": actual_speed,
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
        self.fuzzy_config = FuzzyConfigLoader(settings.FUZZY_CONFIG_PATH)
        self.cabin_controllers: Dict[str, CabinVentilationController] = {
            CabinType.POWER.value: CabinVentilationController(CabinType.POWER, self.fuzzy_config),
            CabinType.WATER.value: CabinVentilationController(CabinType.WATER, self.fuzzy_config),
            CabinType.GAS.value: CabinVentilationController(CabinType.GAS, self.fuzzy_config),
        }
        self._subscribed: bool = False

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

    async def _handle_env_data(self, data: dict):
        try:
            cabin_str = data.get('cabin')
            oxygen = data.get('oxygen')
            temperature = data.get('temperature')
            humidity = data.get('humidity')

            if cabin_str and oxygen is not None and temperature is not None and humidity is not None:
                cabin = CabinType(cabin_str)
                await self.process_sensor_data(cabin, oxygen, temperature, humidity)
        except Exception as e:
            print(f"[通风控制] 处理Redis消息失败: {e}")

    async def start_subscription(self):
        if self._subscribed:
            return
        try:
            await redis_client.subscribe(RedisChannels.ENV_DATA, self._handle_env_data)
            self._subscribed = True
            print("[通风控制] Redis订阅已启动")
        except Exception as e:
            print(f"[通风控制] Redis订阅失败: {e}")


ventilation_controller = VentilationControllerManager()
