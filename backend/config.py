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


settings = Settings()
