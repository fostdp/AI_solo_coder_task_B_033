import asyncio
import json
import random
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

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


@dataclass
class PLCConfig:
    broker: str = "mqtt"
    port: int = 1883
    control_topic: str = "tunnel/control"
    status_topic: str = "tunnel/status"
    telemetry_topic: str = "tunnel/telemetry"
    response_topic_prefix: str = "tunnel/response"
    api_url: str = "http://fastapi:8000"
    num_fans: int = 30
    num_pumps: int = 50
    status_interval: int = 10
    telemetry_interval: int = 60
    enable_mqtt: bool = True
    enable_http_fallback: bool = True
    fan_speed_min: float = 0.0
    fan_speed_max: float = 100.0
    pump_start_level: float = 80.0
    pump_stop_level: float = 30.0
    temperature_normal_min: float = 20.0
    temperature_normal_max: float = 40.0
    temperature_fault_threshold: float = 70.0
    current_running_min: float = 10.0
    current_running_max: float = 50.0
    voltage_nominal: float = 380.0
    voltage_tolerance: float = 5.0
    fault_probability: float = 0.001
    auto_recovery: bool = True
    auto_recovery_time: int = 300

    @classmethod
    def from_env(cls) -> 'PLCConfig':
        config = cls()
        
        config.broker = os.getenv("MQTT_BROKER", config.broker)
        config.port = int(os.getenv("MQTT_PORT", str(config.port)))
        config.control_topic = os.getenv("MQTT_CONTROL_TOPIC", config.control_topic)
        config.status_topic = os.getenv("MQTT_STATUS_TOPIC", config.status_topic)
        config.telemetry_topic = os.getenv("MQTT_TELEMETRY_TOPIC", config.telemetry_topic)
        config.response_topic_prefix = os.getenv("MQTT_RESPONSE_PREFIX", config.response_topic_prefix)
        config.api_url = os.getenv("PLC_API_URL", config.api_url)
        config.num_fans = int(os.getenv("PLC_NUM_FANS", str(config.num_fans)))
        config.num_pumps = int(os.getenv("PLC_NUM_PUMPS", str(config.num_pumps)))
        config.status_interval = int(os.getenv("PLC_STATUS_INTERVAL", str(config.status_interval)))
        config.telemetry_interval = int(os.getenv("PLC_TELEMETRY_INTERVAL", str(config.telemetry_interval)))
        config.enable_mqtt = os.getenv("PLC_ENABLE_MQTT", "true").lower() == "true"
        config.enable_http_fallback = os.getenv("PLC_ENABLE_HTTP_FALLBACK", "true").lower() == "true"
        config.fan_speed_min = float(os.getenv("FAN_SPEED_MIN", str(config.fan_speed_min)))
        config.fan_speed_max = float(os.getenv("FAN_SPEED_MAX", str(config.fan_speed_max)))
        config.pump_start_level = float(os.getenv("PUMP_START_LEVEL", str(config.pump_start_level)))
        config.pump_stop_level = float(os.getenv("PUMP_STOP_LEVEL", str(config.pump_stop_level)))
        config.temperature_normal_min = float(os.getenv("TEMP_NORMAL_MIN", str(config.temperature_normal_min)))
        config.temperature_normal_max = float(os.getenv("TEMP_NORMAL_MAX", str(config.temperature_normal_max)))
        config.temperature_fault_threshold = float(os.getenv("TEMP_FAULT_THRESHOLD", str(config.temperature_fault_threshold)))
        config.fault_probability = float(os.getenv("FAULT_PROBABILITY", str(config.fault_probability)))
        config.auto_recovery = os.getenv("AUTO_RECOVERY", "true").lower() == "true"
        config.auto_recovery_time = int(os.getenv("AUTO_RECOVERY_TIME", str(config.auto_recovery_time)))
        
        return config
    
    def print_config(self):
        logger.info("=" * 60)
        logger.info("MQTT PLC Simulator Configuration")
        logger.info("=" * 60)
        logger.info(f"MQTT Broker: {self.broker}:{self.port}")
        logger.info(f"Control topic: {self.control_topic}")
        logger.info(f"Status topic: {self.status_topic}")
        logger.info(f"Telemetry topic: {self.telemetry_topic}")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Fans: {self.num_fans}")
        logger.info(f"Pumps: {self.num_pumps}")
        logger.info(f"Status interval: {self.status_interval}s")
        logger.info(f"Telemetry interval: {self.telemetry_interval}s")
        logger.info(f"MQTT enabled: {self.enable_mqtt}")
        logger.info(f"HTTP fallback: {self.enable_http_fallback}")
        logger.info(f"Fan speed range: {self.fan_speed_min}% - {self.fan_speed_max}%")
        logger.info(f"Pump levels: start={self.pump_start_level}%, stop={self.pump_stop_level}%")
        logger.info(f"Auto recovery: {self.auto_recovery} ({self.auto_recovery_time}s)")
        logger.info("=" * 60)


class PLCDevice:
    def __init__(self, device_id: str, device_type: str, config: PLCConfig):
        self.device_id = device_id
        self.device_type = device_type
        self.config = config
        self.running = False
        self.speed = 0
        self.fault_count = 0
        self.last_command_time: Optional[datetime] = None
        self.runtime_hours = 0.0
        self.start_count = 0
        self.status = "online"
        self.fault_time: Optional[datetime] = None
        
        self.temperature = 25.0
        self.current = 0.0
        self.voltage = config.voltage_nominal
        self.vibration = 0.5
        self.power_factor = 0.85
        self.energy_consumption = 0.0
        
        self.auto_mode = True
        self.last_status_update: Optional[datetime] = None
    
    def update_telemetry(self):
        if self.status == "fault" and self.config.auto_recovery and self.fault_time:
            recovery_time = (datetime.utcnow() - self.fault_time).total_seconds()
            if recovery_time >= self.config.auto_recovery_time:
                self.status = "online"
                self.fault_count = 0
                self.fault_time = None
                logger.info(f"[{self.device_id}] Auto recovery after {recovery_time:.0f}s")
        
        if self.running and self.status != "fault":
            temp_drift = random.uniform(-0.5, 1.0) if self.running else random.uniform(-1.0, 0.1)
            self.temperature = max(
                self.config.temperature_normal_min,
                min(self.config.temperature_fault_threshold + 10, self.temperature + temp_drift)
            )
            self.current = random.uniform(
                self.config.current_running_min,
                self.config.current_running_max
            ) if self.running else 0.0
            self.vibration = random.uniform(0.5, 2.0) if self.running else 0.1
            self.runtime_hours += 1 / 3600
            self.energy_consumption += (self.current * self.config.voltage_nominal / 1000) * (1 / 3600)
            self.power_factor = random.uniform(0.8, 0.95) if self.running else 0.0
        else:
            temp_drift = random.uniform(-1.0, 0.1)
            self.temperature = max(
                self.config.temperature_normal_min,
                min(self.config.temperature_normal_max, self.temperature + temp_drift)
            )
            self.current = 0.0
            self.vibration = 0.1
            self.power_factor = 0.0
        
        self.voltage = self.config.voltage_nominal + random.uniform(
            -self.config.voltage_tolerance,
            self.config.voltage_tolerance
        )
        
        if self.running and self.status != "fault" and random.random() < self.config.fault_probability:
            self.fault_count += 1
            if self.fault_count > 5:
                self.status = "fault"
                self.fault_time = datetime.utcnow()
                self.running = False
                self.speed = 0
                logger.warning(f"[{self.device_id}] Fault detected! Fault count: {self.fault_count}")
        
        if self.temperature >= self.config.temperature_fault_threshold and self.status != "fault":
            self.status = "fault"
            self.fault_time = datetime.utcnow()
            self.running = False
            self.speed = 0
            logger.warning(f"[{self.device_id}] Over temperature fault: {self.temperature:.1f}°C")
        
        self.last_status_update = datetime.utcnow()
    
    def execute_command(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        self.last_command_time = datetime.utcnow()
        
        result = {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "command": command,
            "success": True,
            "message": "Command executed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.status == "fault" and command != "reset_fault":
            result["success"] = False
            result["message"] = f"Device in fault state, cannot execute {command}"
            logger.warning(f"[{self.device_id}] Rejected {command}: device in fault")
            return result
        
        if self.device_type == "fan":
            if command == "start":
                speed = parameters.get("speed", 50)
                speed = max(self.config.fan_speed_min, min(self.config.fan_speed_max, speed))
                self.running = True
                self.speed = speed
                self.start_count += 1
                result["message"] = f"Fan started at {speed}%"
            
            elif command == "stop":
                self.running = False
                self.speed = 0
                result["message"] = "Fan stopped"
            
            elif command == "set_speed":
                if not self.running:
                    result["success"] = False
                    result["message"] = "Fan is not running"
                else:
                    speed = parameters.get("speed", self.speed)
                    speed = max(self.config.fan_speed_min, min(self.config.fan_speed_max, speed))
                    self.speed = speed
                    result["message"] = f"Fan speed set to {speed}%"
            
            elif command == "reset_fault":
                self.fault_count = 0
                self.status = "online"
                self.fault_time = None
                result["message"] = "Fault reset"
            
            elif command == "set_mode":
                self.auto_mode = parameters.get("auto", True)
                result["message"] = f"Mode set to {'auto' if self.auto_mode else 'manual'}"
            
            else:
                result["success"] = False
                result["message"] = f"Unknown command for fan: {command}"
        
        elif self.device_type == "pump":
            if command == "start":
                self.running = True
                self.start_count += 1
                result["message"] = "Pump started"
            
            elif command == "stop":
                self.running = False
                result["message"] = "Pump stopped"
            
            elif command == "reset_fault":
                self.fault_count = 0
                self.status = "online"
                self.fault_time = None
                result["message"] = "Fault reset"
            
            elif command == "set_mode":
                self.auto_mode = parameters.get("auto", True)
                result["message"] = f"Mode set to {'auto' if self.auto_mode else 'manual'}"
            
            else:
                result["success"] = False
                result["message"] = f"Unknown command for pump: {command}"
        
        else:
            result["success"] = False
            result["message"] = f"Unknown device type: {self.device_type}"
        
        log_level = logger.info if result["success"] else logger.warning
        log_level(f"[{self.device_id}] {command}: {result['message']}")
        return result
    
    def get_status(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "running": self.running,
            "speed": self.speed,
            "status": self.status,
            "auto_mode": self.auto_mode,
            "fault_count": self.fault_count,
            "telemetry": {
                "temperature": round(self.temperature, 2),
                "current": round(self.current, 2),
                "voltage": round(self.voltage, 2),
                "vibration": round(self.vibration, 3),
                "power_factor": round(self.power_factor, 3),
                "energy_consumption": round(self.energy_consumption, 4)
            },
            "statistics": {
                "runtime_hours": round(self.runtime_hours, 2),
                "start_count": self.start_count
            },
            "last_command_time": self.last_command_time.isoformat() if self.last_command_time else None,
            "last_status_update": self.last_status_update.isoformat() if self.last_status_update else None,
            "timestamp": datetime.utcnow().isoformat()
        }


class MQTTPLCSimulator:
    def __init__(self, config: Optional[PLCConfig] = None):
        self.config = config or PLCConfig.from_env()
        
        self.devices: Dict[str, PLCDevice] = {}
        self.client = None
        self.running = False
        self.connected = False
        self.use_mqtt = self.config.enable_mqtt and MQTT_AVAILABLE
        
        self.command_count = 0
        self.status_publish_count = 0
    
    async def load_devices(self):
        logger.info("Loading devices from API...")
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.config.api_url}/api/devices/?limit=500")
                if response.status_code == 200:
                    data = response.json()
                    devices = data.get("devices", [])
                    
                    for device in devices:
                        device_type = device["type"]
                        if device_type in ["fan", "pump"]:
                            plc_device = PLCDevice(device["device_id"], device_type, self.config)
                            self.devices[device["device_id"]] = plc_device
                    
                    fans = len([d for d in self.devices.values() if d.device_type == "fan"])
                    pumps = len([d for d in self.devices.values() if d.device_type == "pump"])
                    logger.info(f"Loaded {fans} fans and {pumps} pumps from API")
                    return
        except Exception as e:
            logger.error(f"Failed to load devices from API: {e}")
        
        self._generate_fallback_devices()
    
    def _generate_fallback_devices(self):
        logger.warning("Using fallback device generation")
        
        for i in range(1, self.config.num_fans + 1):
            device_id = f"fan_{str(i).zfill(4)}"
            self.devices[device_id] = PLCDevice(device_id, "fan", self.config)
        
        for i in range(1, self.config.num_pumps + 1):
            device_id = f"pump_{str(i).zfill(4)}"
            self.devices[device_id] = PLCDevice(device_id, "pump", self.config)
        
        fans = len([d for d in self.devices.values() if d.device_type == "fan"])
        pumps = len([d for d in self.devices.values() if d.device_type == "pump"])
        logger.info(f"Generated {fans} fans and {pumps} pumps")
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            
            control_topics = [
                (self.config.control_topic, 1),
                (f"{self.config.control_topic}/fan/+", 1),
                (f"{self.config.control_topic}/pump/+", 1)
            ]
            
            for topic, qos in control_topics:
                client.subscribe(topic, qos=qos)
                logger.info(f"Subscribed to: {topic}")
            
            self._publish_online_status()
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
            correlation_id = payload.get("correlation_id")
            
            logger.info(
                f"Received command on '{msg.topic}': "
                f"device={device_id}, command={command}"
                f"{', correlation_id=' + correlation_id if correlation_id else ''}"
            )
            
            if not device_id or not command:
                logger.warning("Missing device_id or command in payload")
                return
            
            response = None
            
            if device_id == "all":
                results = []
                for did, device in self.devices.items():
                    if command == "status":
                        results.append(device.get_status())
                    else:
                        result = device.execute_command(command, parameters)
                        results.append(result)
                
                response = {
                    "device_id": "all",
                    "command": command,
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                }
                
            elif device_id in self.devices:
                device = self.devices[device_id]
                
                if command == "status":
                    response = {
                        **device.get_status(),
                        "correlation_id": correlation_id
                    }
                else:
                    result = device.execute_command(command, parameters)
                    response = {
                        **result,
                        "device_status": device.get_status(),
                        "correlation_id": correlation_id
                    }
                
                self.command_count += 1
                
            else:
                logger.warning(f"Unknown device: {device_id}")
                response = {
                    "device_id": device_id,
                    "command": command,
                    "success": False,
                    "message": f"Unknown device: {device_id}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": correlation_id
                }
            
            if response and self.connected:
                response_topic = f"{self.config.response_topic_prefix}/{device_id}"
                client.publish(
                    response_topic,
                    json.dumps(response),
                    qos=1
                )
                logger.debug(f"Published response to {response_topic}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    async def connect_mqtt(self):
        if not self.use_mqtt:
            logger.info("MQTT disabled, using HTTP only")
            return
        
        try:
            client_id = f"plc_simulator_{os.getpid()}_{random.randint(1000, 9999)}"
            self.client = mqtt.Client(
                client_id=client_id,
                protocol=mqtt.MQTTv5
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info(f"Connecting to MQTT broker at {self.config.broker}:{self.config.port}")
            self.client.connect_async(self.config.broker, self.config.port, keepalive=60)
            self.client.loop_start()
            
            for _ in range(50):
                if self.connected:
                    break
                await asyncio.sleep(0.1)
            
            if not self.connected:
                logger.warning("MQTT connection timeout")
                if self.config.enable_http_fallback:
                    logger.info("Switching to HTTP mode")
                    self.use_mqtt = False
                else:
                    raise Exception("MQTT connection failed and HTTP fallback disabled")
                
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            if self.config.enable_http_fallback:
                logger.info("Switching to HTTP mode")
                self.use_mqtt = False
            else:
                raise
    
    def _publish_online_status(self):
        if not self.connected:
            return
        
        status = {
            "simulator_status": "online",
            "num_devices": len(self.devices),
            "num_fans": len([d for d in self.devices.values() if d.device_type == "fan"]),
            "num_pumps": len([d for d in self.devices.values() if d.device_type == "pump"]),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.client.publish(
            f"{self.config.status_topic}/simulator",
            json.dumps(status),
            qos=1,
            retain=True
        )
    
    async def _publish_status(self):
        statuses = []
        
        for device_id, device in self.devices.items():
            device.update_telemetry()
            status = device.get_status()
            statuses.append(status)
            
            if self.use_mqtt and self.connected:
                self.client.publish(
                    f"{self.config.status_topic}/{device_id}",
                    json.dumps(status),
                    qos=0
                )
        
        if self.use_mqtt and self.connected and statuses:
            batch_status = {
                "devices": statuses,
                "timestamp": datetime.utcnow().isoformat()
            }
            self.client.publish(
                self.config.status_topic,
                json.dumps(batch_status),
                qos=0
            )
        
        self.status_publish_count += 1
        
        if self.status_publish_count % 10 == 0:
            logger.info(
                f"Published status for {len(statuses)} devices "
                f"(total commands: {self.command_count})"
            )
    
    async def _publish_telemetry(self):
        if not self.use_mqtt or not self.connected:
            return
        
        telemetry_batch = []
        for device_id, device in self.devices.items():
            telemetry_batch.append({
                "device_id": device_id,
                "device_type": device.device_type,
                "running": device.running,
                "timestamp": datetime.utcnow().isoformat(),
                **device.get_status()["telemetry"]
            })
        
        if telemetry_batch:
            self.client.publish(
                self.config.telemetry_topic,
                json.dumps({"data": telemetry_batch}),
                qos=0
            )
    
    async def _poll_http_commands(self):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.config.api_url}/api/control/pending-commands?limit=50"
                )
                if response.status_code == 200:
                    data = response.json()
                    commands = data.get("commands", [])
                    
                    for cmd in commands:
                        device_id = cmd.get("device_id")
                        command = cmd.get("command")
                        parameters = cmd.get("parameters", {})
                        
                        if device_id in self.devices:
                            device = self.devices[device_id]
                            result = device.execute_command(command, parameters)
                            
                            async with httpx.AsyncClient(timeout=5.0) as ack_client:
                                await ack_client.post(
                                    f"{self.config.api_url}/api/control/commands/{cmd.get('id')}/ack",
                                    json=result
                                )
                            
                            logger.info(f"Processed HTTP command: {device_id} {command}")
                            
        except Exception as e:
            logger.debug(f"HTTP poll error: {e}")
    
    async def _send_sensor_data(self):
        data_batch = []
        for device_id, device in self.devices.items():
            status = device.get_status()
            data = {
                "device_id": device_id,
                "type": device.device_type,
                "timestamp": status["timestamp"],
                "running": device.running,
                "speed": device.speed,
                "temperature": status["telemetry"]["temperature"],
                "current": status["telemetry"]["current"],
                "voltage": status["telemetry"]["voltage"],
                "vibration": status["telemetry"]["vibration"]
            }
            data_batch.append(data)
        
        if data_batch:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{self.config.api_url}/api/sensor/data/batch",
                        json=data_batch
                    )
            except Exception as e:
                logger.debug(f"Failed to send sensor data: {e}")
    
    async def run(self):
        self.running = True
        self.config.print_config()
        
        await self.load_devices()
        
        if self.config.enable_mqtt:
            await self.connect_mqtt()
        
        logger.info("Starting MQTT PLC Simulator...")
        logger.info(f"Controlling {len(self.devices)} devices")
        
        status_counter = 0
        telemetry_counter = 0
        
        while self.running:
            try:
                await self._publish_status()
                
                if not self.use_mqtt and self.config.enable_http_fallback:
                    await self._poll_http_commands()
                
                status_counter += 1
                telemetry_counter += 1
                
                if status_counter >= 6:
                    await self._send_sensor_data()
                    status_counter = 0
                
                if telemetry_counter >= (self.config.telemetry_interval // self.config.status_interval):
                    await self._publish_telemetry()
                    telemetry_counter = 0
                
                await asyncio.sleep(self.config.status_interval)
                
            except KeyboardInterrupt:
                logger.info("Received stop signal")
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                await asyncio.sleep(5)
        
        self._cleanup()
        logger.info("PLC Simulator stopped")
    
    def _cleanup(self):
        if self.client and self.use_mqtt:
            try:
                offline_status = {
                    "simulator_status": "offline",
                    "timestamp": datetime.utcnow().isoformat()
                }
                self.client.publish(
                    f"{self.config.status_topic}/simulator",
                    json.dumps(offline_status),
                    qos=1,
                    retain=True
                )
                self.client.loop_stop()
                self.client.disconnect()
            except Exception as e:
                logger.debug(f"Cleanup error: {e}")
    
    def stop(self):
        self.running = False
    
    def simulate_fault(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].status = "fault"
            self.devices[device_id].fault_count = 6
            self.devices[device_id].fault_time = datetime.utcnow()
            self.devices[device_id].running = False
            self.devices[device_id].speed = 0
            logger.warning(f"Simulated fault on {device_id}")
    
    def simulate_recovery(self, device_id: str):
        if device_id in self.devices:
            self.devices[device_id].status = "online"
            self.devices[device_id].fault_count = 0
            self.devices[device_id].fault_time = None
            logger.info(f"Simulated recovery on {device_id}")
    
    def get_statistics(self) -> Dict[str, Any]:
        fans = [d for d in self.devices.values() if d.device_type == "fan"]
        pumps = [d for d in self.devices.values() if d.device_type == "pump"]
        
        return {
            "total_devices": len(self.devices),
            "fans": {
                "total": len(fans),
                "running": sum(1 for d in fans if d.running),
                "fault": sum(1 for d in fans if d.status == "fault")
            },
            "pumps": {
                "total": len(pumps),
                "running": sum(1 for d in pumps if d.running),
                "fault": sum(1 for d in pumps if d.status == "fault")
            },
            "commands_processed": self.command_count,
            "status_updates": self.status_publish_count,
            "mqtt_connected": self.connected,
            "mqtt_enabled": self.use_mqtt
        }


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="MQTT PLC Simulator")
    parser.add_argument("--broker", default=None,
                        help="MQTT broker address (overrides MQTT_BROKER env var)")
    parser.add_argument("--port", type=int, default=None,
                        help="MQTT broker port (overrides MQTT_PORT env var)")
    parser.add_argument("--api-url", default=None,
                        help="Backend API URL (overrides PLC_API_URL env var)")
    parser.add_argument("--interval", type=int, default=None,
                        help="Status report interval (overrides PLC_STATUS_INTERVAL env var)")
    parser.add_argument("--num-fans", type=int, default=None,
                        help="Number of fans (overrides PLC_NUM_FANS env var)")
    parser.add_argument("--num-pumps", type=int, default=None,
                        help="Number of pumps (overrides PLC_NUM_PUMPS env var)")
    parser.add_argument("--print-config", action="store_true",
                        help="Print configuration and exit")
    parser.add_argument("--print-stats", action="store_true",
                        help="Print statistics while running")
    
    args = parser.parse_args()
    
    config = PLCConfig.from_env()
    
    if args.broker:
        config.broker = args.broker
    if args.port:
        config.port = args.port
    if args.api_url:
        config.api_url = args.api_url
    if args.interval:
        config.status_interval = args.interval
    if args.num_fans:
        config.num_fans = args.num_fans
    if args.num_pumps:
        config.num_pumps = args.num_pumps
    
    if args.print_config:
        config.print_config()
        return
    
    simulator = MQTTPLCSimulator(config=config)
    
    if args.print_stats:
        async def print_stats():
            while simulator.running:
                stats = simulator.get_statistics()
                logger.info(f"Stats: {json.dumps(stats)}")
                await asyncio.sleep(60)
        
        asyncio.create_task(print_stats())
    
    await simulator.run()


if __name__ == "__main__":
    asyncio.run(main())
