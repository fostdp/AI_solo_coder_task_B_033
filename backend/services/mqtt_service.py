import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from backend.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed, using simulated MQTT")


class MQTTService:
    def __init__(self):
        self.available = MQTT_AVAILABLE
        self.client: Optional[Any] = None
        self.connected = False
        self.message_handlers: Dict[str, Callable] = {}
        self.simulated_mode = not MQTT_AVAILABLE
        self._simulated_messages: asyncio.Queue = asyncio.Queue()
        self._status_callbacks = []
    
    def add_status_callback(self, callback: Callable):
        self._status_callbacks.append(callback)
    
    async def connect(self):
        if self.simulated_mode:
            logger.info("Starting simulated MQTT connection")
            self.connected = True
            asyncio.create_task(self._simulated_message_loop())
            return
        
        try:
            self.client = mqtt.Client(
                client_id=f"backend_control_{asyncio.get_event_loop().time()}",
                protocol=mqtt.MQTTv5
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            self.client.connect_async(
                host=settings.MQTT_BROKER,
                port=settings.MQTT_PORT,
                keepalive=60
            )
            self.client.loop_start()
            
            for _ in range(30):
                if self.connected:
                    break
                await asyncio.sleep(0.1)
            
            if not self.connected:
                logger.warning("MQTT connection timeout, switching to simulated mode")
                self.simulated_mode = True
                self.connected = True
                asyncio.create_task(self._simulated_message_loop())
            
        except Exception as e:
            logger.error(f"MQTT connection failed: {e}, switching to simulated mode")
            self.simulated_mode = True
            self.connected = True
            asyncio.create_task(self._simulated_message_loop())
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            logger.info("MQTT connected successfully")
            client.subscribe(settings.MQTT_TOPIC_STATUS, qos=1)
            for callback in self._status_callbacks:
                callback(True)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.connected = False
        logger.warning(f"MQTT disconnected with code {rc}")
        for callback in self._status_callbacks:
            callback(False)
    
    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic = msg.topic
            
            if topic in self.message_handlers:
                handler = self.message_handlers[topic]
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(payload))
                else:
                    handler(payload)
            
            for callback in self._status_callbacks:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(payload))
            
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")
    
    async def _simulated_message_loop(self):
        while True:
            try:
                msg = await asyncio.wait_for(self._simulated_messages.get(), timeout=1.0)
                topic = msg.get("topic", settings.MQTT_TOPIC_STATUS)
                payload = msg.get("payload", {})
                
                if topic in self.message_handlers:
                    handler = self.message_handlers[topic]
                    if asyncio.iscoroutinefunction(handler):
                        await handler(payload)
                    else:
                        handler(payload)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in simulated MQTT loop: {e}")
    
    def register_handler(self, topic: str, handler: Callable):
        self.message_handlers[topic] = handler
        if self.available and self.connected and not self.simulated_mode:
            self.client.subscribe(topic, qos=1)
    
    async def publish_control_command(self, device_id: str, command: str, 
                                       parameters: Dict[str, Any]):
        payload = {
            "device_id": device_id,
            "command": command,
            "parameters": parameters,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.simulated_mode:
            await self._simulated_messages.put({
                "topic": settings.MQTT_TOPIC_CONTROL,
                "payload": payload
            })
            logger.info(f"Simulated MQTT publish: {device_id} {command}")
            
            response_payload = {
                "device_id": device_id,
                "status": "executed",
                "command": command,
                "parameters": parameters,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self._simulated_messages.put({
                "topic": settings.MQTT_TOPIC_STATUS,
                "payload": response_payload
            })
        else:
            try:
                self.client.publish(
                    topic=settings.MQTT_TOPIC_CONTROL,
                    payload=json.dumps(payload),
                    qos=1
                )
                logger.info(f"MQTT publish: {device_id} {command}")
            except Exception as e:
                logger.error(f"MQTT publish failed: {e}")
                await self._simulated_messages.put({
                    "topic": settings.MQTT_TOPIC_CONTROL,
                    "payload": payload
                })
        
        return payload
    
    async def publish_status_update(self, device_id: str, status: Dict[str, Any]):
        payload = {
            "device_id": device_id,
            **status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.simulated_mode:
            await self._simulated_messages.put({
                "topic": settings.MQTT_TOPIC_STATUS,
                "payload": payload
            })
        else:
            try:
                self.client.publish(
                    topic=settings.MQTT_TOPIC_STATUS,
                    payload=json.dumps(payload),
                    qos=0
                )
            except Exception as e:
                logger.error(f"MQTT status publish failed: {e}")
    
    async def disconnect(self):
        if self.available and self.client and not self.simulated_mode:
            self.client.loop_stop()
            self.client.disconnect()
        self.connected = False


mqtt_service = MQTTService()
