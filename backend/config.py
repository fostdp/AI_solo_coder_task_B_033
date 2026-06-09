from typing import Dict
from pydantic import BaseModel


class Settings(BaseModel):
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "utility_tunnel"
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_TOPIC_CONTROL: str = "tunnel/control"
    MQTT_TOPIC_STATUS: str = "tunnel/status"
    LORA_GATEWAY_URL: str = "http://localhost:8000/api/sensor/data"
    SMS_API_URL: str = "http://localhost:8000/api/sms/send"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_CHANNEL_SENSOR_DATA: str = "tunnel:sensor:data"
    REDIS_CHANNEL_ALARM_EVENT: str = "tunnel:alarm:event"
    REDIS_CHANNEL_DEVICE_STATUS: str = "tunnel:device:status"
    REDIS_CHANNEL_CONTROL_COMMAND: str = "tunnel:control:command"
    FUZZY_RULES_PATH: str = "config/fuzzy_rules.yaml"
    
    OXYGEN_MIN: float = 19.0
    OXYGEN_MAX: float = 21.0
    TEMPERATURE_MAX: float = 35.0
    METHANE_ALARM: float = 1.0
    H2S_ALARM: float = 10.0
    OXYGEN_ALARM_LOW: float = 18.0
    PUMP_LEVEL_HIGH: float = 80.0
    PUMP_LEVEL_LOW: float = 30.0
    PUMP_DELAY: int = 60
    
    PID_KP: float = 2.0
    PID_KI: float = 0.5
    PID_KD: float = 0.1
    
    TUNNEL_LENGTH: float = 15.0
    NUM_ENV_SENSORS: int = 200
    NUM_MANHOLE_SENSORS: int = 100
    NUM_PUMPS: int = 50
    NUM_FANS: int = 30
    FANS_PER_CHAMBER: int = 10
    CHAMBERS: list = ["电力舱", "水信舱", "燃气舱", "综合"]

    NUM_FIBER_SENSORS: int = 100
    NUM_SMOKE_SENSORS: int = 60
    NUM_INSPECTION_ROBOTS: int = 5
    NUM_FIRE_DOORS: int = 16
    NUM_FIRE_EXTINGUISHERS: int = 50

    STRUCTURE_STRAIN_WARNING: float = 200.0
    STRUCTURE_STRAIN_ALARM: float = 400.0
    STRUCTURE_CRACK_WARNING: float = 0.2
    STRUCTURE_CRACK_ALARM: float = 0.5
    FIBER_BREAK_STRAIN_THRESHOLD: float = -500.0
    FIBER_BREAK_DETECTION_WINDOW: int = 3
    FIBER_DATA_TIMEOUT_SECONDS: int = 30
    FIBER_INTERPOLATION_MAX_GAP: float = 0.5

    FIRE_TEMP_RATE_WARNING: float = 2.0
    FIRE_TEMP_RATE_ALARM: float = 5.0
    FIRE_SMOKE_DENSITY_WARNING: float = 5.0
    FIRE_SMOKE_DENSITY_ALARM: float = 15.0
    FIRE_PROBABILITY_THRESHOLD: float = 0.7

    ROBOT_SPEED: float = 1.0
    ROBOT_BATTERY_FULL: float = 100.0
    ROBOT_BATTERY_LOW: float = 20.0
    ROBOT_AVOID_HIGH_TEMP: float = 40.0
    ROBOT_AVOID_HIGH_HUMIDITY: float = 80.0
    ROBOT_AVOID_GAS_METHANE: float = 0.5
    ROBOT_AVOID_GAS_H2S: float = 5.0
    ROBOT_TOPOLOGY_MAP_FILE: str = "data/topology_map.json"
    ROBOT_PATH_PLANNING_ATTEMPTS: int = 3
    ROBOT_BRANCH_STABILITY_THRESHOLD: float = 0.7
    ROBOT_GLOBAL_PLANNING_WEIGHT: Dict[str, float] = {
        "distance": 0.4,
        "safety": 0.3,
        "energy": 0.2,
        "time": 0.1
    }

    ASSET_LIFE_PREDICTION_MODEL: str = "rule_based"
    MAINTENANCE_MONTHLY_PRIORITY_WEIGHT: float = 1.5
    MAINTENANCE_RISK_WEIGHT: float = 2.0

    FIRE_WELDING_TEMP_FLUCTUATION: float = 5.0
    FIRE_WELDING_CYCLE_SECONDS: int = 60
    FIRE_WELDING_SMOKE_THRESHOLD: float = 3.0
    FIRE_HUMAN_CONFIRM_TIMEOUT: int = 300
    FIRE_HEAT_SOURCE_DURATION_MIN: int = 5
    FIRE_TEMP_DISTRIBUTION_THRESHOLD: float = 10.0

    ASSET_REPLACEMENT_SERIAL_CHANGE: bool = True
    ASSET_REPLACEMENT_INSTALL_DATE_THRESHOLD_DAYS: int = 7
    ASSET_REPLACEMENT_PROPERTY_CHANGE_THRESHOLD: float = 0.3
    ASSET_REPLACEMENT_AUTO_SYNC: bool = True
    ASSET_REPLACEMENT_AUDIT_LOG_ENABLED: bool = True

    ROBOT_PATH_PLANNER_PROCESS_PORT: int = 8002
    ROBOT_PATH_PLANNER_QUEUE_TIMEOUT: float = 5.0
    ROBOT_PATH_PLANNER_MAX_RETRIES: int = 3

    FIRE_INFERENCE_SERVICE_PORT: int = 8001
    FIRE_INFERENCE_SERVICE_HOST: str = "127.0.0.1"
    FIRE_INFERENCE_SERVICE_TIMEOUT: float = 10.0
    FIRE_INFERENCE_SERVICE_MAX_RETRIES: int = 3


settings = Settings()
