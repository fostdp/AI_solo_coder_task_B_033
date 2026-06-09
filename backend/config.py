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

    ASSET_LIFE_PREDICTION_MODEL: str = "rule_based"
    MAINTENANCE_MONTHLY_PRIORITY_WEIGHT: float = 1.5
    MAINTENANCE_RISK_WEIGHT: float = 2.0


settings = Settings()
