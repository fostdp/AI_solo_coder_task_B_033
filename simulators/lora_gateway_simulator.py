import asyncio
import json
import random
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Any
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LoRaGatewaySimulator:
    def __init__(self, api_url: str = "http://localhost:8000/api/sensor/data"):
        self.api_url = api_url
        self.env_sensors: List[Dict[str, Any]] = []
        self.manhole_sensors: List[Dict[str, Any]] = []
        self.pumps: List[Dict[str, Any]] = []
        self.running = False
        self.interval = 60
        
        self.anomaly_mode = False
        self.anomaly_sensors: List[str] = []
    
    async def load_devices(self):
        logger.info("Loading devices from API...")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_url.rsplit('/', 2)[0]}/devices/?limit=500")
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("devices", [])
                    
                    self.env_sensors = [d for d in devices if d["type"] == "env_sensor"]
                    self.manhole_sensors = [d for d in devices if d["type"] == "manhole"]
                    self.pumps = [d for d in devices if d["type"] == "pump"]
                    
                    logger.info(f"Loaded {len(self.env_sensors)} environment sensors")
                    logger.info(f"Loaded {len(self.manhole_sensors)} manhole sensors")
                    logger.info(f"Loaded {len(self.pumps)} pumps")
                    
                    for sensor in self.env_sensors:
                        sensor["current_temp"] = 22 + random.uniform(-3, 5)
                        sensor["current_humidity"] = 55 + random.uniform(-10, 15)
                        sensor["current_oxygen"] = 20.5 + random.uniform(-0.5, 0.5)
                        sensor["current_methane"] = 0.02 + random.uniform(0, 0.05)
                        sensor["current_h2s"] = 1 + random.uniform(0, 3)
                    
                    for pump in self.pumps:
                        pump["current_level"] = 30 + random.uniform(-10, 20)
                        pump["last_level_change"] = time.time()
                    
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            self._generate_fallback_devices()
    
    def _generate_fallback_devices(self):
        logger.warning("Using fallback device generation")
        
        for i in range(1, 201):
            self.env_sensors.append({
                "device_id": f"env_sensor_{str(i).zfill(4)}",
                "current_temp": 22 + random.uniform(-3, 5),
                "current_humidity": 55 + random.uniform(-10, 15),
                "current_oxygen": 20.5 + random.uniform(-0.5, 0.5),
                "current_methane": 0.02 + random.uniform(0, 0.05),
                "current_h2s": 1 + random.uniform(0, 3)
            })
        
        for i in range(1, 101):
            self.manhole_sensors.append({
                "device_id": f"manhole_{str(i).zfill(4)}",
                "cover_open": False
            })
        
        for i in range(1, 51):
            self.pumps.append({
                "device_id": f"pump_{str(i).zfill(4)}",
                "current_level": 30 + random.uniform(-10, 20),
                "last_level_change": time.time()
            })
    
    def _update_env_sensor_values(self, sensor: Dict[str, Any]):
        drift = random.uniform(-0.3, 0.3)
        sensor["current_temp"] = max(15, min(40, sensor["current_temp"] + drift))
        
        drift = random.uniform(-1, 1)
        sensor["current_humidity"] = max(30, min(95, sensor["current_humidity"] + drift))
        
        drift = random.uniform(-0.05, 0.05)
        sensor["current_oxygen"] = max(16, min(23, sensor["current_oxygen"] + drift))
        
        drift = random.uniform(-0.005, 0.01)
        sensor["current_methane"] = max(0, min(2, sensor["current_methane"] + drift))
        
        drift = random.uniform(-0.3, 0.5)
        sensor["current_h2s"] = max(0, min(20, sensor["current_h2s"] + drift))
        
        if self.anomaly_mode and sensor["device_id"] in self.anomaly_sensors:
            sensor["current_oxygen"] = random.uniform(16, 17.5)
            sensor["current_methane"] = random.uniform(0.8, 1.5)
            sensor["current_h2s"] = random.uniform(8, 15)
    
    def _update_pump_level(self, pump: Dict[str, Any]):
        now = time.time()
        time_since_change = now - pump["last_level_change"]
        
        if random.random() < 0.05 or time_since_change > 300:
            if pump["current_level"] > 70:
                pump["current_level"] -= random.uniform(5, 15)
            elif pump["current_level"] < 40:
                pump["current_level"] += random.uniform(5, 20)
            else:
                pump["current_level"] += random.uniform(-10, 10)
            
            pump["current_level"] = max(10, min(95, pump["current_level"]))
            pump["last_level_change"] = now
        
        if self.anomaly_mode and pump["device_id"] in self.anomaly_sensors:
            pump["current_level"] = random.uniform(85, 95)
    
    async def _send_sensor_data(self, data: List[Dict[str, Any]]):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/batch",
                    json=data,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Sent {len(data)} readings - processed: {result.get('processed')}, failed: {result.get('failed')}")
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
                "location": sensor.get("location")
            }
            readings.append(reading)
        return readings
    
    async def _generate_manhole_readings(self) -> List[Dict[str, Any]]:
        readings = []
        for sensor in self.manhole_sensors:
            cover_open = False
            
            if random.random() < 0.005:
                cover_open = True
                logger.warning(f"Simulating illegal manhole opening: {sensor['device_id']}")
            
            if self.anomaly_mode and sensor["device_id"] in self.anomaly_sensors:
                cover_open = True
            
            reading = {
                "device_id": sensor["device_id"],
                "type": "manhole",
                "timestamp": datetime.utcnow().isoformat(),
                "cover_open": cover_open,
                "location": sensor.get("location")
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
                "location": pump.get("location")
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
        
        batch_size = 50
        for i in range(0, len(all_readings), batch_size):
            batch = all_readings[i:i + batch_size]
            await self._send_sensor_data(batch)
            await asyncio.sleep(0.5)
    
    async def run_continuous(self):
        self.running = True
        logger.info(f"Starting LoRa gateway simulator (interval: {self.interval}s)")
        
        await self.load_devices()
        
        if not self.env_sensors:
            logger.error("No devices loaded, cannot run simulator")
            return
        
        while self.running:
            try:
                start_time = time.time()
                
                await self.run_once()
                
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval - elapsed)
                
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
    
    def enable_anomaly_mode(self, sensor_ids: List[str] = None):
        self.anomaly_mode = True
        if sensor_ids:
            self.anomaly_sensors = sensor_ids
        else:
            all_ids = [s["device_id"] for s in self.env_sensors[:10]]
            all_ids += [s["device_id"] for s in self.manhole_sensors[:3]]
            all_ids += [p["device_id"] for p in self.pumps[:2]]
            self.anomaly_sensors = all_ids
        logger.info(f"Anomaly mode enabled for {len(self.anomaly_sensors)} devices")
    
    def disable_anomaly_mode(self):
        self.anomaly_mode = False
        self.anomaly_sensors = []
        logger.info("Anomaly mode disabled")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LoRa Gateway Simulator")
    parser.add_argument("--api-url", default="http://localhost:8000/api/sensor/data",
                        help="API endpoint URL")
    parser.add_argument("--interval", type=int, default=60,
                        help="Reporting interval in seconds")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit")
    parser.add_argument("--anomaly", action="store_true",
                        help="Enable anomaly simulation")
    
    args = parser.parse_args()
    
    simulator = LoRaGatewaySimulator(api_url=args.api_url)
    simulator.interval = args.interval
    
    if args.anomaly:
        simulator.enable_anomaly_mode()
    
    if args.once:
        await simulator.load_devices()
        await simulator.run_once()
    else:
        await simulator.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
