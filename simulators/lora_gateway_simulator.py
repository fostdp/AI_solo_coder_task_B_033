import asyncio
import json
import random
import logging
import httpx
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SimulatorConfig:
    api_url: str = "http://fastapi:8000/api/sensor/data"
    interval: int = 60
    num_env_sensors: int = 200
    num_manhole_sensors: int = 100
    num_pumps: int = 50
    batch_size: int = 50
    
    temp_range: tuple = (-3, 5)
    humidity_range: tuple = (-10, 15)
    oxygen_range: tuple = (-0.5, 0.5)
    
    methane_min: float = 0.0
    methane_max: float = 2.0
    methane_normal_min: float = 0.0
    methane_normal_max: float = 0.1
    methane_anomaly_min: float = 0.8
    methane_anomaly_max: float = 1.5
    
    h2s_min: float = 0.0
    h2s_max: float = 20.0
    h2s_normal_min: float = 0.0
    h2s_normal_max: float = 5.0
    h2s_anomaly_min: float = 8.0
    h2s_anomaly_max: float = 15.0
    
    oxygen_min: float = 16.0
    oxygen_max: float = 23.0
    oxygen_normal_min: float = 19.0
    oxygen_normal_max: float = 21.5
    oxygen_anomaly_min: float = 16.0
    oxygen_anomaly_max: float = 17.5
    
    temperature_min: float = 15.0
    temperature_max: float = 40.0
    
    humidity_min: float = 30.0
    humidity_max: float = 95.0
    
    level_min: float = 10.0
    level_max: float = 95.0
    level_high_threshold: float = 70.0
    level_low_threshold: float = 40.0
    
    anomaly_mode: bool = False
    anomaly_sensor_ratio: float = 0.05
    manhole_open_probability: float = 0.005

    @classmethod
    def from_env(cls) -> 'SimulatorConfig':
        config = cls()
        
        config.api_url = os.getenv("LORA_API_URL", config.api_url)
        config.interval = int(os.getenv("LORA_INTERVAL", str(config.interval)))
        config.num_env_sensors = int(os.getenv("LORA_NUM_ENV_SENSORS", str(config.num_env_sensors)))
        config.num_manhole_sensors = int(os.getenv("LORA_NUM_MANHOLE_SENSORS", str(config.num_manhole_sensors)))
        config.num_pumps = int(os.getenv("LORA_NUM_PUMPS", str(config.num_pumps)))
        config.batch_size = int(os.getenv("LORA_BATCH_SIZE", str(config.batch_size)))
        
        config.methane_min = float(os.getenv("METHANE_MIN", str(config.methane_min)))
        config.methane_max = float(os.getenv("METHANE_MAX", str(config.methane_max)))
        config.methane_normal_min = float(os.getenv("METHANE_NORMAL_MIN", str(config.methane_normal_min)))
        config.methane_normal_max = float(os.getenv("METHANE_NORMAL_MAX", str(config.methane_normal_max)))
        config.methane_anomaly_min = float(os.getenv("METHANE_ANOMALY_MIN", str(config.methane_anomaly_min)))
        config.methane_anomaly_max = float(os.getenv("METHANE_ANOMALY_MAX", str(config.methane_anomaly_max)))
        
        config.h2s_min = float(os.getenv("H2S_MIN", str(config.h2s_min)))
        config.h2s_max = float(os.getenv("H2S_MAX", str(config.h2s_max)))
        config.h2s_normal_min = float(os.getenv("H2S_NORMAL_MIN", str(config.h2s_normal_min)))
        config.h2s_normal_max = float(os.getenv("H2S_NORMAL_MAX", str(config.h2s_normal_max)))
        config.h2s_anomaly_min = float(os.getenv("H2S_ANOMALY_MIN", str(config.h2s_anomaly_min)))
        config.h2s_anomaly_max = float(os.getenv("H2S_ANOMALY_MAX", str(config.h2s_anomaly_max)))
        
        config.oxygen_min = float(os.getenv("OXYGEN_MIN", str(config.oxygen_min)))
        config.oxygen_max = float(os.getenv("OXYGEN_MAX", str(config.oxygen_max)))
        config.oxygen_normal_min = float(os.getenv("OXYGEN_NORMAL_MIN", str(config.oxygen_normal_min)))
        config.oxygen_normal_max = float(os.getenv("OXYGEN_NORMAL_MAX", str(config.oxygen_normal_max)))
        config.oxygen_anomaly_min = float(os.getenv("OXYGEN_ANOMALY_MIN", str(config.oxygen_anomaly_min)))
        config.oxygen_anomaly_max = float(os.getenv("OXYGEN_ANOMALY_MAX", str(config.oxygen_anomaly_max)))
        
        config.temperature_min = float(os.getenv("TEMPERATURE_MIN", str(config.temperature_min)))
        config.temperature_max = float(os.getenv("TEMPERATURE_MAX", str(config.temperature_max)))
        
        config.humidity_min = float(os.getenv("HUMIDITY_MIN", str(config.humidity_min)))
        config.humidity_max = float(os.getenv("HUMIDITY_MAX", str(config.humidity_max)))
        
        config.anomaly_mode = os.getenv("LORA_ANOMALY_MODE", "false").lower() == "true"
        config.anomaly_sensor_ratio = float(os.getenv("LORA_ANOMALY_RATIO", str(config.anomaly_sensor_ratio)))
        config.manhole_open_probability = float(os.getenv("MANHOLE_OPEN_PROB", str(config.manhole_open_probability)))
        
        return config
    
    def print_config(self):
        logger.info("=" * 60)
        logger.info("LoRa Gateway Simulator Configuration")
        logger.info("=" * 60)
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Reporting interval: {self.interval}s")
        logger.info(f"Environment sensors: {self.num_env_sensors}")
        logger.info(f"Manhole sensors: {self.num_manhole_sensors}")
        logger.info(f"Pumps: {self.num_pumps}")
        logger.info(f"Batch size: {self.batch_size}")
        logger.info(f"Anomaly mode: {'ENABLED' if self.anomaly_mode else 'disabled'}")
        if self.anomaly_mode:
            logger.info(f"Anomaly sensor ratio: {self.anomaly_sensor_ratio * 100:.0f}%")
        logger.info(f"Methane range: {self.methane_min}% - {self.methane_max}%")
        logger.info(f"H2S range: {self.h2s_min}ppm - {self.h2s_max}ppm")
        logger.info(f"Oxygen range: {self.oxygen_min}% - {self.oxygen_max}%")
        logger.info(f"Temperature range: {self.temperature_min}°C - {self.temperature_max}°C")
        logger.info(f"Humidity range: {self.humidity_min}% - {self.humidity_max}%")
        logger.info("=" * 60)


class LoRaGatewaySimulator:
    def __init__(self, config: Optional[SimulatorConfig] = None):
        self.config = config or SimulatorConfig.from_env()
        self.env_sensors: List[Dict[str, Any]] = []
        self.manhole_sensors: List[Dict[str, Any]] = []
        self.pumps: List[Dict[str, Any]] = []
        self.running = False
        self.anomaly_sensors: List[str] = []
    
    async def load_devices(self):
        logger.info("Loading devices from API...")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.config.api_url.rsplit('/', 2)[0]}/devices/?limit=500"
                )
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("devices", [])
                    
                    self.env_sensors = [d for d in devices if d["type"] == "env_sensor"]
                    self.manhole_sensors = [d for d in devices if d["type"] == "manhole"]
                    self.pumps = [d for d in devices if d["type"] == "pump"]
                    
                    logger.info(f"Loaded {len(self.env_sensors)} environment sensors")
                    logger.info(f"Loaded {len(self.manhole_sensors)} manhole sensors")
                    logger.info(f"Loaded {len(self.pumps)} pumps")
                    
                    self._initialize_sensor_values()
                    
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            self._generate_fallback_devices()
    
    def _initialize_sensor_values(self):
        for sensor in self.env_sensors:
            sensor["current_temp"] = 22 + random.uniform(*self.config.temp_range)
            sensor["current_humidity"] = 55 + random.uniform(*self.config.humidity_range)
            sensor["current_oxygen"] = random.uniform(self.config.oxygen_normal_min, self.config.oxygen_normal_max)
            sensor["current_methane"] = random.uniform(self.config.methane_normal_min, self.config.methane_normal_max)
            sensor["current_h2s"] = random.uniform(self.config.h2s_normal_min, self.config.h2s_normal_max)
        
        for pump in self.pumps:
            pump["current_level"] = 30 + random.uniform(-10, 20)
            pump["last_level_change"] = time.time()
    
    def _generate_fallback_devices(self):
        logger.warning("Using fallback device generation")
        logger.info(f"Generating {self.config.num_env_sensors} environment sensors")
        
        for i in range(1, self.config.num_env_sensors + 1):
            self.env_sensors.append({
                "device_id": f"env_sensor_{str(i).zfill(4)}",
                "current_temp": 22 + random.uniform(*self.config.temp_range),
                "current_humidity": 55 + random.uniform(*self.config.humidity_range),
                "current_oxygen": random.uniform(self.config.oxygen_normal_min, self.config.oxygen_normal_max),
                "current_methane": random.uniform(self.config.methane_normal_min, self.config.methane_normal_max),
                "current_h2s": random.uniform(self.config.h2s_normal_min, self.config.h2s_normal_max),
                "chamber": random.choice(["电力舱", "水信舱", "燃气舱", "综合"]),
                "distance_km": round(random.uniform(0, 15), 2)
            })
        
        logger.info(f"Generating {self.config.num_manhole_sensors} manhole sensors")
        for i in range(1, self.config.num_manhole_sensors + 1):
            self.manhole_sensors.append({
                "device_id": f"manhole_{str(i).zfill(4)}",
                "cover_open": False,
                "chamber": random.choice(["电力舱", "水信舱", "燃气舱", "综合"]),
                "distance_km": round(random.uniform(0, 15), 2)
            })
        
        logger.info(f"Generating {self.config.num_pumps} pumps")
        for i in range(1, self.config.num_pumps + 1):
            self.pumps.append({
                "device_id": f"pump_{str(i).zfill(4)}",
                "current_level": 30 + random.uniform(-10, 20),
                "last_level_change": time.time(),
                "chamber": random.choice(["电力舱", "水信舱", "燃气舱", "综合"]),
                "distance_km": round(random.uniform(0, 15), 2)
            })
    
    def _update_env_sensor_values(self, sensor: Dict[str, Any]):
        is_anomaly = self.config.anomaly_mode and sensor["device_id"] in self.anomaly_sensors
        
        drift = random.uniform(-0.3, 0.3)
        sensor["current_temp"] = max(
            self.config.temperature_min,
            min(self.config.temperature_max, sensor["current_temp"] + drift)
        )
        
        drift = random.uniform(-1, 1)
        sensor["current_humidity"] = max(
            self.config.humidity_min,
            min(self.config.humidity_max, sensor["current_humidity"] + drift)
        )
        
        drift = random.uniform(-0.05, 0.05)
        if is_anomaly:
            sensor["current_oxygen"] = random.uniform(
                self.config.oxygen_anomaly_min,
                self.config.oxygen_anomaly_max
            )
        else:
            sensor["current_oxygen"] = max(
                self.config.oxygen_min,
                min(self.config.oxygen_max, sensor["current_oxygen"] + drift)
            )
        
        drift = random.uniform(-0.005, 0.01)
        if is_anomaly:
            sensor["current_methane"] = random.uniform(
                self.config.methane_anomaly_min,
                self.config.methane_anomaly_max
            )
        else:
            sensor["current_methane"] = max(
                self.config.methane_min,
                min(self.config.methane_max, sensor["current_methane"] + drift)
            )
        
        drift = random.uniform(-0.3, 0.5)
        if is_anomaly:
            sensor["current_h2s"] = random.uniform(
                self.config.h2s_anomaly_min,
                self.config.h2s_anomaly_max
            )
        else:
            sensor["current_h2s"] = max(
                self.config.h2s_min,
                min(self.config.h2s_max, sensor["current_h2s"] + drift)
            )
    
    def _update_pump_level(self, pump: Dict[str, Any]):
        is_anomaly = self.config.anomaly_mode and pump["device_id"] in self.anomaly_sensors
        now = time.time()
        time_since_change = now - pump["last_level_change"]
        
        if is_anomaly:
            pump["current_level"] = random.uniform(85, 95)
        else:
            if random.random() < 0.05 or time_since_change > 300:
                if pump["current_level"] > self.config.level_high_threshold:
                    pump["current_level"] -= random.uniform(5, 15)
                elif pump["current_level"] < self.config.level_low_threshold:
                    pump["current_level"] += random.uniform(5, 20)
                else:
                    pump["current_level"] += random.uniform(-10, 10)
                
                pump["current_level"] = max(
                    self.config.level_min,
                    min(self.config.level_max, pump["current_level"])
                )
                pump["last_level_change"] = now
    
    async def _send_sensor_data(self, data: List[Dict[str, Any]]):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.config.api_url}/batch",
                    json=data,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"Sent {len(data)} readings - "
                        f"processed: {result.get('processed')}, "
                        f"failed: {result.get('failed')}"
                    )
                else:
                    logger.warning(f"API responded with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send sensor data: {e}")
    
    async def _generate_env_sensor_readings(self) -> List[Dict[str, Any]]:
        readings = []
        for sensor in self.env_sensors:
            self._update_env_sensor_values(sensor)
            
            reading = {
                "device_id": sensor["device_id"],
                "type": "env_sensor",
                "timestamp": datetime.utcnow().isoformat(),
                "temperature": round(sensor["current_temp"], 2),
                "humidity": round(sensor["current_humidity"], 2),
                "oxygen": round(sensor["current_oxygen"], 2),
                "methane": round(sensor["current_methane"], 4),
                "h2s": round(sensor["current_h2s"], 2),
                "chamber": sensor.get("chamber"),
                "distance_km": sensor.get("distance_km")
            }
            readings.append(reading)
        return readings
    
    async def _generate_manhole_readings(self) -> List[Dict[str, Any]]:
        readings = []
        for sensor in self.manhole_sensors:
            cover_open = False
            
            if random.random() < self.config.manhole_open_probability:
                cover_open = True
                logger.warning(f"Simulating illegal manhole opening: {sensor['device_id']}")
            
            if self.config.anomaly_mode and sensor["device_id"] in self.anomaly_sensors:
                cover_open = True
            
            reading = {
                "device_id": sensor["device_id"],
                "type": "manhole",
                "timestamp": datetime.utcnow().isoformat(),
                "cover_open": cover_open,
                "chamber": sensor.get("chamber"),
                "distance_km": sensor.get("distance_km")
            }
            readings.append(reading)
        return readings
    
    async def _generate_pump_readings(self) -> List[Dict[str, Any]]:
        readings = []
        for pump in self.pumps:
            self._update_pump_level(pump)
            
            reading = {
                "device_id": pump["device_id"],
                "type": "pump",
                "timestamp": datetime.utcnow().isoformat(),
                "level": round(pump["current_level"], 2),
                "running": pump.get("running", False),
                "chamber": pump.get("chamber"),
                "distance_km": pump.get("distance_km")
            }
            readings.append(reading)
        return readings
    
    async def run_once(self):
        logger.info("Generating sensor readings...")
        
        env_readings = await self._generate_env_sensor_readings()
        manhole_readings = await self._generate_manhole_readings()
        pump_readings = await self._generate_pump_readings()
        
        all_readings = env_readings + manhole_readings + pump_readings
        logger.info(f"Generated {len(all_readings)} total readings")
        
        for i in range(0, len(all_readings), self.config.batch_size):
            batch = all_readings[i:i + self.config.batch_size]
            await self._send_sensor_data(batch)
            await asyncio.sleep(0.5)
    
    def _select_anomaly_sensors(self):
        if not self.config.anomaly_mode:
            return
        
        num_anomaly_env = max(1, int(len(self.env_sensors) * self.config.anomaly_sensor_ratio))
        num_anomaly_manhole = max(1, int(len(self.manhole_sensors) * self.config.anomaly_sensor_ratio))
        num_anomaly_pump = max(1, int(len(self.pumps) * self.config.anomaly_sensor_ratio))
        
        self.anomaly_sensors = [
            s["device_id"] for s in random.sample(self.env_sensors, num_anomaly_env)
        ] + [
            s["device_id"] for s in random.sample(self.manhole_sensors, num_anomaly_manhole)
        ] + [
            p["device_id"] for p in random.sample(self.pumps, num_anomaly_pump)
        ]
        
        logger.info(f"Selected {len(self.anomaly_sensors)} anomaly sensors:")
        for s in self.anomaly_sensors[:10]:
            logger.info(f"  - {s}")
        if len(self.anomaly_sensors) > 10:
            logger.info(f"  ... and {len(self.anomaly_sensors) - 10} more")
    
    async def run_continuous(self):
        self.running = True
        self.config.print_config()
        
        await self.load_devices()
        
        if not self.env_sensors:
            logger.error("No devices loaded, cannot run simulator")
            return
        
        self._select_anomaly_sensors()
        
        logger.info(f"Starting LoRa gateway simulator (interval: {self.config.interval}s)")
        
        while self.running:
            try:
                start_time = time.time()
                
                await self.run_once()
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.config.interval - elapsed)
                
                logger.info(f"Cycle complete in {elapsed:.2f}s, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logger.info("Received stop signal")
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                await asyncio.sleep(5)
        
        logger.info("LoRa gateway simulator stopped")
    
    def stop(self):
        self.running = False


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LoRa Gateway Simulator")
    parser.add_argument("--api-url", default=None,
                        help="API endpoint URL (overrides LORA_API_URL env var)")
    parser.add_argument("--interval", type=int, default=None,
                        help="Reporting interval in seconds (overrides LORA_INTERVAL env var)")
    parser.add_argument("--num-env-sensors", type=int, default=None,
                        help="Number of environment sensors (overrides LORA_NUM_ENV_SENSORS env var)")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit")
    parser.add_argument("--anomaly", action="store_true",
                        help="Enable anomaly simulation (overrides LORA_ANOMALY_MODE env var)")
    parser.add_argument("--print-config", action="store_true",
                        help="Print configuration and exit")
    
    args = parser.parse_args()
    
    config = SimulatorConfig.from_env()
    
    if args.api_url:
        config.api_url = args.api_url
    if args.interval:
        config.interval = args.interval
    if args.num_env_sensors:
        config.num_env_sensors = args.num_env_sensors
    if args.anomaly:
        config.anomaly_mode = True
    
    if args.print_config:
        config.print_config()
        return
    
    simulator = LoRaGatewaySimulator(config=config)
    
    if args.once:
        await simulator.load_devices()
        await simulator.run_once()
    else:
        await simulator.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
