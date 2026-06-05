import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "地下管廊综合监控系统"
    APP_VERSION: str = "1.0.0"
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB: str = os.getenv("pipe_corridor")
    MQTT_BROKER: str = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", 1883))
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")
    LORA_API_URL: str = os.getenv("LORA_API_URL", "http://localhost:8000")
    SMS_API_URL: str = os.getenv("SMS_API_URL", "http://localhost:8001/sms")
    OXYGEN_MIN: float = 19.0
    OXYGEN_MAX: float = 21.0
    TEMP_MAX: float = 35.0
    METHANE_ALARM: float = 1.0
    H2S_ALARM: float = 10.0
    OXYGEN_DANGER: float = 18.0
    PUMP_START_LEVEL: float = 0.8
    PUMP_STOP_LEVEL: float = 0.3
    PUMP_DELAY: int = 30
    class Config:
        env_file = ".env"


settings = Settings()
