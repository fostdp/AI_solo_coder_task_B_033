import asyncio
import logging
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from backend.config import settings
from backend.models.schemas import (
    DeviceType,
    DeviceStatus,
    ControlCommand,
    OperationLog,
    FanControlParams
)
from backend.models.database import (
    devices_collection,
    control_commands_collection,
    operation_logs_collection,
    serialize_document
)
from backend.services.mqtt_service import mqtt_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MembershipFunction:
    def __init__(self, mf_type: str, params: List[float]):
        self.type = mf_type
        self.params = params

    def evaluate(self, x: float) -> float:
        if self.type == "triangle":
            return self._triangle(x)
        elif self.type == "trapezoid":
            return self._trapezoid(x)
        elif self.type == "singleton":
            return self._singleton(x)
        else:
            raise ValueError(f"Unknown membership function type: {self.type}")

    def _triangle(self, x: float) -> float:
        a, b, c = self.params
        if x <= a or x >= c:
            return 0.0
        elif a < x <= b:
            return (x - a) / (b - a) if b != a else 1.0
        else:
            return (c - x) / (c - b) if c != b else 1.0

    def _trapezoid(self, x: float) -> float:
        a, b, c, d = self.params
        if x <= a or x >= d:
            return 0.0
        elif a < x < b:
            return (x - a) / (b - a) if b != a else 1.0
        elif b <= x <= c:
            return 1.0
        else:
            return (d - x) / (d - c) if d != c else 1.0

    def _singleton(self, x: float) -> float:
        a = self.params[0]
        return 1.0 if abs(x - a) < 1e-6 else 0.0


class FuzzyVariable:
    def __init__(self, name: str, var_range: Tuple[float, float], 
                 membership_functions: Dict[str, Dict[str, Any]]):
        self.name = name
        self.range = var_range
        self.membership_functions: Dict[str, MembershipFunction] = {}
        
        for mf_name, mf_config in membership_functions.items():
            self.membership_functions[mf_name] = MembershipFunction(
                mf_type=mf_config["type"],
                params=mf_config["params"]
            )

    def fuzzify(self, value: float) -> Dict[str, float]:
        result = {}
        for mf_name, mf in self.membership_functions.items():
            result[mf_name] = mf.evaluate(value)
        return result


class FuzzyRule:
    def __init__(self, rule_id: int, condition: Dict[str, str], 
                 action: Dict[str, str], weight: float = 1.0,
                 description: str = ""):
        self.id = rule_id
        self.condition = condition
        self.action = action
        self.weight = weight
        self.description = description

    def evaluate(self, fuzzified_inputs: Dict[str, Dict[str, float]]) -> float:
        firing_strengths = []
        
        for var_name, mf_name in self.condition.items():
            if var_name in fuzzified_inputs:
                mf_value = fuzzified_inputs[var_name].get(mf_name, 0.0)
                firing_strengths.append(mf_value)
        
        if not firing_strengths:
            return 0.0
        
        return min(firing_strengths) * self.weight


class FuzzyController:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.input_variables: Dict[str, FuzzyVariable] = {}
        self.output_variable: Optional[FuzzyVariable] = None
        self.rules: List[FuzzyRule] = []
        
        self._initialize_variables()
        self._initialize_rules()

    def _initialize_variables(self):
        input_vars_config = self.config.get("input_variables", {})
        
        for var_name, var_config in input_vars_config.items():
            self.input_variables[var_name] = FuzzyVariable(
                name=var_name,
                var_range=tuple(var_config["range"]),
                membership_functions=var_config["membership_functions"]
            )
        
        output_var_config = self.config.get("output_variable", {})
        for var_name, var_config in output_var_config.items():
            self.output_variable = FuzzyVariable(
                name=var_name,
                var_range=tuple(var_config["range"]),
                membership_functions=var_config["membership_functions"]
            )
            break

    def _initialize_rules(self):
        rules_config = self.config.get("rule_base", [])
        
        for rule_config in rules_config:
            self.rules.append(FuzzyRule(
                rule_id=rule_config["id"],
                condition=rule_config["condition"],
                action=rule_config["action"],
                weight=rule_config.get("weight", 1.0),
                description=rule_config.get("description", "")
            ))

    def infer(self, inputs: Dict[str, float]) -> Tuple[float, Dict[str, Any]]:
        fuzzified_inputs = {}
        
        for var_name, value in inputs.items():
            if var_name in self.input_variables:
                fuzzified_inputs[var_name] = self.input_variables[var_name].fuzzify(value)
        
        rule_firings = []
        for rule in self.rules:
            firing_strength = rule.evaluate(fuzzified_inputs)
            if firing_strength > 0:
                rule_firings.append({
                    "rule_id": rule.id,
                    "firing_strength": firing_strength,
                    "action": rule.action,
                    "description": rule.description
                })
        
        output_mf_name = list(self.config["output_variable"].keys())[0]
        aggregated = self._mamdani_inference(rule_firings, output_mf_name)
        
        crisp_value = self._defuzzify_centroid(aggregated, output_mf_name)
        
        control_params = self.config.get("control_parameters", {})
        min_speed = control_params.get("min_fan_speed", 0)
        max_speed = control_params.get("max_fan_speed", 100)
        crisp_value = max(min_speed, min(max_speed, crisp_value))
        
        debug_info = {
            "inputs": inputs,
            "fuzzified_inputs": fuzzified_inputs,
            "rule_firings": rule_firings,
            "aggregated_output": aggregated,
            "crisp_output": crisp_value
        }
        
        return crisp_value, debug_info

    def _mamdani_inference(self, rule_firings: List[Dict[str, Any]], 
                            output_var_name: str) -> Dict[str, float]:
        aggregated = defaultdict(float)
        
        for firing in rule_firings:
            firing_strength = firing["firing_strength"]
            action_mf = firing["action"][output_var_name]
            
            if action_mf in aggregated:
                aggregated[action_mf] = max(aggregated[action_mf], firing_strength)
            else:
                aggregated[action_mf] = firing_strength
        
        return dict(aggregated)

    def _defuzzify_centroid(self, aggregated: Dict[str, float], 
                             output_var_name: str) -> float:
        if not aggregated or self.output_variable is None:
            return 0.0
        
        output_range = self.output_variable.range
        step = (output_range[1] - output_range[0]) / 1000
        
        numerator = 0.0
        denominator = 0.0
        
        x = output_range[0]
        while x <= output_range[1]:
            mf_values = []
            for mf_name, firing_strength in aggregated.items():
                if mf_name in self.output_variable.membership_functions:
                    mf = self.output_variable.membership_functions[mf_name]
                    mf_value = min(mf.evaluate(x), firing_strength)
                    mf_values.append(mf_value)
            
            aggregated_value = max(mf_values) if mf_values else 0.0
            
            numerator += x * aggregated_value * step
            denominator += aggregated_value * step
            
            x += step
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator


class ChamberVentilation:
    def __init__(self, chamber: str, fuzzy_controller: FuzzyController):
        self.chamber = chamber
        self.fuzzy_controller = fuzzy_controller
        self.fan_ids: List[str] = []
        self.last_sensor_data: Dict[str, float] = {
            "oxygen": 20.0,
            "temperature": 25.0,
            "humidity": 60.0
        }
        self.last_control_time: Optional[datetime] = None
        self.last_speed: int = 0
        self.last_running: bool = False
        self.control_history: List[Dict[str, Any]] = []

    async def load_fans(self):
        fans = await devices_collection.find({
            "type": DeviceType.FAN,
            "chamber": self.chamber,
            "status": {"$ne": DeviceStatus.FAULT}
        }).to_list(length=settings.FANS_PER_CHAMBER + 5)
        
        self.fan_ids = [fan["device_id"] for fan in fans[:settings.FANS_PER_CHAMBER]]
        logger.info(f"Chamber {self.chamber} loaded {len(self.fan_ids)} fans")

    def update_sensor_data(self, oxygen: float, temperature: float, humidity: float):
        if oxygen is not None:
            self.last_sensor_data["oxygen"] = oxygen
        if temperature is not None:
            self.last_sensor_data["temperature"] = temperature
        if humidity is not None:
            self.last_sensor_data["humidity"] = humidity

    def calculate_control(self) -> Tuple[bool, int, Dict[str, Any]]:
        speed, debug_info = self.fuzzy_controller.infer(self.last_sensor_data)
        
        speed_threshold = self.fuzzy_controller.config.get(
            "control_parameters", {}
        ).get("speed_threshold", 5)
        
        running = speed > speed_threshold
        speed_int = int(round(speed)) if running else 0
        
        control_params = self.fuzzy_controller.config.get("control_parameters", {})
        emergency_oxygen = control_params.get("emergency_oxygen_threshold", 17)
        emergency_temp = control_params.get("emergency_temperature_threshold", 38)
        
        if (self.last_sensor_data["oxygen"] < emergency_oxygen or 
            self.last_sensor_data["temperature"] > emergency_temp):
            running = True
            speed_int = 100
            debug_info["emergency_mode"] = True
        
        control_details = {
            "chamber": self.chamber,
            **self.last_sensor_data,
            "fuzzy_debug": debug_info,
            "running": running,
            "speed": speed_int,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.last_running = running
        self.last_speed = speed_int
        self.last_control_time = datetime.utcnow()
        self.control_history.append(control_details)
        
        if len(self.control_history) > 100:
            self.control_history = self.control_history[-100:]
        
        return running, speed_int, control_details


class VentilationController:
    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.running = False
        self.fuzzy_config: Optional[Dict[str, Any]] = None
        self.chamber_controllers: Dict[str, ChamberVentilation] = {}
        self.fan_last_control: Dict[str, datetime] = {}
        self.sensor_data_buffer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.control_interval = 30

    async def load_fuzzy_config(self) -> bool:
        try:
            config_path = Path(settings.FUZZY_RULES_PATH)
            if not config_path.exists():
                config_path = Path(__file__).parent.parent.parent / settings.FUZZY_RULES_PATH
            
            with open(config_path, "r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f)
            
            self.fuzzy_config = full_config.get("ventilation_control", {})
            if not self.fuzzy_config:
                logger.error("ventilation_control section not found in fuzzy rules config")
                return False
            
            logger.info(f"Loaded fuzzy config: {self.fuzzy_config.get('name', 'Unknown')} "
                       f"v{self.fuzzy_config.get('version', '1.0')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load fuzzy config: {e}")
            return False

    async def initialize(self):
        if not await self.load_fuzzy_config():
            raise RuntimeError("Failed to load fuzzy configuration")
        
        fuzzy_controller = FuzzyController(self.fuzzy_config)
        
        for chamber in settings.CHAMBERS:
            self.chamber_controllers[chamber] = ChamberVentilation(
                chamber=chamber,
                fuzzy_controller=fuzzy_controller
            )
            await self.chamber_controllers[chamber].load_fans()
        
        self.control_interval = self.fuzzy_config.get(
            "control_parameters", {}
        ).get("control_interval", 30)
        
        logger.info(f"VentilationController initialized with {len(self.chamber_controllers)} chambers")

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
            logger.info("Redis connected successfully")
            
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(settings.REDIS_CHANNEL_SENSOR_DATA)
            logger.info(f"Subscribed to Redis channel: {settings.REDIS_CHANNEL_SENSOR_DATA}")
            
        except Exception as e:
            logger.error(f"Redis connection failed: {e}, using in-memory mode")
            self.redis_client = None

    async def disconnect_redis(self):
        if self.pubsub:
            await self.pubsub.unsubscribe()
            self.pubsub = None
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
        logger.info("Redis disconnected")

    async def process_sensor_message(self, message: Dict[str, Any]):
        try:
            device_id = message.get("device_id")
            sensor_type = message.get("type")
            chamber = message.get("chamber", "综合")
            data = message.get("data", {})
            
            if sensor_type != "env_sensor":
                return
            
            oxygen = data.get("oxygen")
            temperature = data.get("temperature")
            humidity = data.get("humidity")
            
            if oxygen is None and temperature is None:
                return
            
            if chamber not in self.chamber_controllers:
                self.chamber_controllers[chamber] = ChamberVentilation(
                    chamber=chamber,
                    fuzzy_controller=FuzzyController(self.fuzzy_config)
                )
                await self.chamber_controllers[chamber].load_fans()
            
            chamber_controller = self.chamber_controllers[chamber]
            chamber_controller.update_sensor_data(oxygen, temperature, humidity)
            
            self.sensor_data_buffer[chamber].append({
                "device_id": device_id,
                "oxygen": oxygen,
                "temperature": temperature,
                "humidity": humidity,
                "timestamp": datetime.utcnow()
            })
            
            if len(self.sensor_data_buffer[chamber]) > 50:
                self.sensor_data_buffer[chamber] = self.sensor_data_buffer[chamber][-50:]
            
            await self._process_chamber_control(chamber)
            
        except Exception as e:
            logger.error(f"Error processing sensor message: {e}")

    async def _process_chamber_control(self, chamber: str):
        if chamber not in self.chamber_controllers:
            return
        
        chamber_controller = self.chamber_controllers[chamber]
        now = datetime.utcnow()
        
        if (chamber_controller.last_control_time and 
            (now - chamber_controller.last_control_time).total_seconds() < self.control_interval):
            return
        
        running, speed, control_details = chamber_controller.calculate_control()
        
        control_actions = []
        
        for fan_id in chamber_controller.fan_ids:
            last_control = self.fan_last_control.get(fan_id)
            if (last_control and 
                (now - last_control).total_seconds() < self.control_interval):
                continue
            
            fan = await devices_collection.find_one({"device_id": fan_id})
            if not fan:
                continue
            
            current_state = fan.get("properties", {})
            current_running = current_state.get("running", False)
            current_speed = current_state.get("speed", 0)
            
            speed_diff = abs(current_speed - speed)
            if current_running != running or speed_diff > 5:
                action = await self._control_fan(fan_id, running, speed, control_details)
                if action:
                    control_actions.append(action)
                self.fan_last_control[fan_id] = now
        
        await self._publish_control_command(chamber, running, speed, control_details, control_actions)

    async def _control_fan(self, fan_id: str, running: bool, speed: int,
                           control_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            FanControlParams(running=running, speed=speed)
        except ValueError as e:
            logger.error(f"Invalid fan control parameters for {fan_id}: {e}")
            return None
        
        command = ControlCommand(
            device_id=fan_id,
            command="set_fan_speed" if running else "stop_fan",
            parameters={"running": running, "speed": speed, "control_details": control_details},
            source="fuzzy_control"
        )
        
        await control_commands_collection.insert_one(command.dict())
        
        await mqtt_service.publish_control_command(
            device_id=fan_id,
            command=command.command,
            parameters=command.parameters
        )
        
        await devices_collection.update_one(
            {"device_id": fan_id},
            {"$set": {
                "properties.running": running,
                "properties.speed": speed,
                "properties.last_control_time": datetime.utcnow(),
                "properties.control_source": "fuzzy_control"
            }}
        )
        
        log = OperationLog(
            device_id=fan_id,
            action="fan_control",
            details={"running": running, "speed": speed, "source": "fuzzy_control"},
            operator="system"
        )
        await operation_logs_collection.insert_one(log.dict())
        
        return {
            "device_id": fan_id,
            "running": running,
            "speed": speed,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _publish_control_command(self, chamber: str, running: bool, speed: int,
                                        control_details: Dict[str, Any],
                                        control_actions: List[Dict[str, Any]]):
        if not self.redis_client:
            return
        
        message = {
            "chamber": chamber,
            "running": running,
            "speed": speed,
            "control_details": control_details,
            "control_actions": control_actions,
            "fan_count": len(control_actions),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            await self.redis_client.publish(
                settings.REDIS_CHANNEL_CONTROL_COMMAND,
                json.dumps(message, ensure_ascii=False)
            )
            logger.info(f"Published control command for chamber {chamber}: "
                       f"running={running}, speed={speed}, fans={len(control_actions)}")
        except Exception as e:
            logger.error(f"Failed to publish control command: {e}")

    async def _redis_listener_loop(self):
        if not self.pubsub:
            logger.warning("Redis pubsub not available, skipping listener loop")
            return
        
        logger.info("Starting Redis listener loop for ventilation control")
        
        try:
            async for message in self.pubsub.listen():
                if not self.running:
                    break
                
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self.process_sensor_message(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse Redis message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")
                        
        except Exception as e:
            logger.error(f"Error in Redis listener loop: {e}")
        finally:
            logger.info("Redis listener loop stopped")

    async def start(self):
        if self.running:
            logger.warning("VentilationController is already running")
            return
        
        await self.initialize()
        await self.connect_redis()
        self.running = True
        
        if self.redis_client and self.pubsub:
            asyncio.create_task(self._redis_listener_loop())
            logger.info("VentilationController started with Redis listener")
        else:
            logger.info("VentilationController started in in-memory mode")

    async def stop(self):
        self.running = False
        await self.disconnect_redis()
        logger.info("VentilationController stopped")

    async def manual_control(self, chamber: str, running: bool, speed: int,
                             operator: str = "manual") -> Dict[str, Any]:
        if chamber not in self.chamber_controllers:
            raise ValueError(f"Chamber {chamber} not found")
        
        chamber_controller = self.chamber_controllers[chamber]
        control_details = {
            "chamber": chamber,
            "running": running,
            "speed": speed,
            "source": "manual",
            "operator": operator,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        control_actions = []
        for fan_id in chamber_controller.fan_ids:
            action = await self._control_fan(fan_id, running, speed, control_details)
            if action:
                control_actions.append(action)
            self.fan_last_control[fan_id] = datetime.utcnow()
        
        chamber_controller.last_running = running
        chamber_controller.last_speed = speed
        chamber_controller.last_control_time = datetime.utcnow()
        
        await self._publish_control_command(chamber, running, speed, control_details, control_actions)
        
        return {
            "chamber": chamber,
            "running": running,
            "speed": speed,
            "control_actions": control_actions,
            "fan_count": len(control_actions)
        }

    def get_chamber_status(self, chamber: str) -> Optional[Dict[str, Any]]:
        if chamber not in self.chamber_controllers:
            return None
        
        controller = self.chamber_controllers[chamber]
        return {
            "chamber": chamber,
            "sensor_data": controller.last_sensor_data,
            "running": controller.last_running,
            "speed": controller.last_speed,
            "last_control_time": controller.last_control_time.isoformat() 
                if controller.last_control_time else None,
            "fan_ids": controller.fan_ids,
            "fan_count": len(controller.fan_ids)
        }

    def get_all_chamber_statuses(self) -> Dict[str, Dict[str, Any]]:
        return {
            chamber: self.get_chamber_status(chamber)
            for chamber in self.chamber_controllers
        }
    
    async def start_control_loop(self):
        await self.start()
    
    async def stop_control_loop(self):
        await self.stop()


ventilation_controller = VentilationController()
