import asyncio
import json
import random
import logging
from datetime import datetime
from typing import Dict, Any, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed, using HTTP fallback mode")


class PLCDevice:
    def __init__(self, device_id: str, device_type: str):
        self.device_id = device_id
        self.device_type = device_type
        self.running = False
        self.speed = 0
        self.fault_count = 0
        self.last_command_time = None
        self.runtime_hours = 0.0
        self.start_count = 0
        self.status = "online"
        
        self.temperature = 25.0
        self.current = 0.0
        self.voltage = 380.0
        self.vibration = 0.5
    
    def update_telemetry(self):
        if self.running:
            self.temperature += random.uniform(-0.5, 1.0)
            self.current = random.uniform(10, 50) if self.running else 0
            self.vibration = random.uniform(0.5, 2.0) if self.running else 0.2
            self.runtime_hours += 1/60/60
        else:
            self.temperature += random.uniform(-1.0, 0.1)
            self.current = 0.0
            self.vibration = 0.1
        
        self.temperature = max(20, min(80, self.temperature))
        self.voltage = 380 + random.uniform(-5, 5)
        
        if self.running and random.random() < 0.001:
            self.fault_count += 1
            if self.fault_count > 5:
                self.status = "fault"
                logger.warning(f"Device {self.device_id} fault detected!")
    
    def execute_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        self.last_command_time = datetime.utcnow()
        
        result = {
            "device_id": self.device_id,
            "command": command,
            "success": True,
            "message": "Command executed"
        }
        
        if self.device_type == "fan":
            if command == "set_fan_speed":
                self.running = parameters.get("running", False)
                self.speed = parameters.get("speed", 0)
                if self.running:
                    self.start_count += 1
                result["message"] = f"Fan speed set to {self.speed}%"
                
            elif command == "stop_fan":
                self.running = False
                self.speed = 0
                result["message"] = "Fan stopped"
                
            elif command == "reset_fault":
                self.fault_count = 0
                self.status = "online"
                result["message"] = "Fault reset"
        
        elif self.device_type == "pump":
            if command == "start_pump":
                self.running = True
                self.start_count += 1
                result["message"] = "Pump started"
                
            elif command == "stop_pump":
                self.running = False
                result["message"] = "Pump stopped"
                
            elif command == "reset_fault":
                self.fault_count = 0
                self.status = "online"
                result["message"] = "Fault reset"
        
        logger.info(f"[{self.device_id}] {command}: {result['message']}")
        return result
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "running": self.running,
            "speed": self.speed,
            "status": self.status,
            "fault_count": self.fault_count,
            "telemetry": {
                "temperature": round(self.temperature, 2),
                "current": round(self.current, 2),
                "voltage": round(self.voltage, 2),
                "vibration": round(self.vibration, 3)
            },
            "statistics": {
                "runtime_hours": round(self.runtime_hours, 2),
                "start_count": self.start_count
            },
            "last_command_time": self.last_command_time.isoformat() if self.last_command_time else None
        }


class MQTTPLCSimulator:
    def __init__(self, broker: str = "localhost", port: int = 1883,
                 control_topic: str = "tunnel/control",
                 status_topic: str = "tunnel/status",
                 api_url: str = "http://localhost:8000"):
        self.broker = broker
        self.port = port
        self.control_topic = control_topic
        self.status_topic = status_topic
        self.api_url = api_url
        
        self.devices: Dict[str, PLCDevice] = {}
        self.client = None
        self.running = False
        self.connected = False
        self.use_mqtt = MQTT_AVAILABLE
        
        self.status_interval = 10
    
    async def load_devices(self):
        logger.info("Loading devices from API...")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_url}/api/devices/?limit=500")
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("devices", [])
                    
                    for device in devices:
                        device_type = device["type"]
                        if device_type in ["fan", "pump"]:
                            plc_device = PLCDevice(device["device_id"], device_type)
                            self.devices[device["device_id"]] = plc_device
                    
                    logger.info(f"Loaded {len([d for d in self.devices.values() if d.device_type == 'fan'])} fans")
                    logger.info(f"Loaded {len([d for d in self.devices.values() if d.device_type == 'pump'])} pumps")
                    
        except Exception as e:
            logger.error(f"Failed to load devices: {e}")
            self._generate_fallback_devices()
    
    def _generate_fallback_devices(self):
        logger.warning("Using fallback device generation")
        
        for i in range(1, 31):
            device_id = f"fan_{str(i).zfill(4)}"
            self.devices[device_id] = PLCDevice(device_id, "fan")
        
        for i in range(1, 51):
            device_id = f"pump_{str(i).zfill(4)}"
            self.devices[device_id] = PLCDevice(device_id, "pump")
        
        logger.info(f"Generated {len(self.devices)} simulated devices")
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            client.subscribe(self.control_topic, qos=1)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.connected = False
        logger.warning(f"Disconnected from MQTT broker (code {rc})")
    
    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            device_id = payload.get("device_id")
            command = payload.get("command")
            parameters = payload.get("parameters", {})
            
            logger.info(f"Received command: {device_id} - {command}")
            
            if device_id in self.devices:
                device = self.devices[device_id]
                result = device.execute_command(command, parameters)
                
                response = {
                    **result,
                    "timestamp": datetime.utcnow().isoformat(),
                    "device_status": device.get_status()
                }
                
                client.publish(
                    self.status_topic,
                    json.dumps(response),
                    qos=1
                )
                
                logger.info(f"Command result: {result['success']} - {result['message']}")
            else:
                logger.warning(f"Unknown device: {device_id}")
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    async def connect_mqtt(self):
        if not self.use_mqtt:
            logger.info("MQTT not available, using HTTP mode")
            return
        
        try:
            self.client = mqtt.Client(
                client_id=f"plc_simulator_{random.randint(1000, 9999)}",
                protocol=mqtt.MQTTv5
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            for _ in range(30):
                if self.connected:
                    break
                await asyncio.sleep(0.1)
            
            if not self.connected:
                logger.warning("MQTT connection timeout, switching to HTTP mode")
                self.use_mqtt = False
                
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}, switching to HTTP mode")
            self.use_mqtt = False
    
    async def _publish_status(self):
        for device_id, device in self.devices.items():
            device.update_telemetry()
            
            status = device.get_status()
            
            if self.use_mqtt and self.connected:
                self.client.publish(
                    self.status_topic,
                    json.dumps(status),
                    qos=0
                )
            else:
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        await client.post(
                            f"{self.api_url}/api/sensor/data",
                            json={
                                "device_id": device_id,
                                "type": device.device_type,
                                "timestamp": status["timestamp"],
                                "running": device.running,
                                "speed": device.speed,
                                "temperature": status["telemetry"]["temperature"]
                            }
                        )
                except Exception as e:
                    pass
    
    async def _poll_http_commands(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.api_url}/api/control/commands?limit=10"
                )
                if response.status_code == 200:
                    data = response.json()
                    commands = data.get("commands", [])
                    
                    for cmd in commands:
                        device_id = cmd.get("device_id")
                        command = cmd.get("command")
                        parameters = cmd.get("parameters", {})
                        source = cmd.get("source", "automatic")
                        
                        if source == "manual" and device_id in self.devices:
                            device = self.devices[device_id]
                            device.execute_command(command, parameters)
                            
        except Exception as e:
            pass
    
    async def _send_sensor_data(self):
        data_batch = []
        for device_id, device in self.devices.items():
            status = device.get_status()
            data = {
                "device_id": device_id,
                "type": device.device_type,
                "timestamp": datetime.utcnow().isoformat(),
                "running": device.running,
                "speed": device.speed,
                "temperature": status["telemetry"]["temperature"]
            }
            data_batch.append(data)
        
        if data_batch:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{self.api_url}/api/sensor/data/batch",
                        json=data_batch
                    )
            except Exception as e:
                logger.debug(f"Failed to send sensor data: {e}")
    
    async def run(self):
        self.running = True
        logger.info("Starting MQTT PLC Simulator...")
        
        await self.load_devices()
        await self.connect_mqtt()
        
        status_counter = 0
        
        while self.running:
            try:
                await self._publish_status()
                
                if not self.use_mqtt:
                    await self._poll_http_commands()
                
                status_counter += 1
                if status_counter >= 6:
                    await self._send_sensor_data()
                    status_counter = 0
                
                await asyncio.sleep(self.status_interval)
                
            except KeyboardInterrupt:
                logger.info("Received stop signal")
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                await asyncio.sleep(5)
        
        if self.client and self.use_mqtt:
            self.client.loop_stop()
            self.client.disconnect()
        
        logger.info("PLC Simulator stopped")
    
    def stop(self):
        self.running = False
    
    def simulate_fault(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].status = "fault"
            self.devices[device_id].fault_count = 6
            logger.warning(f"Simulated fault on {device_id}")
    
    def simulate_recovery(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].status = "online"
            self.devices[device_id].fault_count = 0
            logger.info(f"Simulated recovery on {device_id}")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT PLC Simulator")
    parser.add_argument("--broker", default="localhost", help="MQTT broker address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--interval", type=int, default=10, help="Status report interval")
    
    args = parser.parse_args()
    
    simulator = MQTTPLCSimulator(
        broker=args.broker,
        port=args.port,
        api_url=args.api_url
    )
    simulator.status_interval = args.interval
    
    await simulator.run()


if __name__ == "__main__":
    asyncio.run(main())
