import json
import time
import random
import threading
import os
import sys
from datetime import datetime
from typing import Dict
import paho.mqtt.client as mqtt


class PLCDevice:
    def __init__(self, device_id: str, device_type: str, cabin: str, config: Dict = None):
        self.device_id = device_id
        self.device_type = device_type
        self.cabin = cabin
        self.is_running = False
        self.target_speed = 0
        self.current_speed = 0
        self.current = 0.0
        self.vibration = 0.0
        self.level = random.uniform(0.1, 0.4)
        self.flow_rate = 0.0
        self.running_hours = random.uniform(0, 1000)
        self.fault_simulated = False
        self.config = config or {}
        self.last_command_time = 0

    def update(self, delta_time: float):
        if self.device_type == "fan":
            if self.is_running:
                speed_diff = self.target_speed - self.current_speed
                self.current_speed += speed_diff * 0.1 * delta_time
                self.current = 3.0 + (self.current_speed / 100) * 8.0 + random.uniform(-0.5, 0.5)
                self.vibration = 1.5 + (self.current_speed / 100) * 3.0 + random.uniform(-0.3, 0.3)
                self.running_hours += delta_time / 3600
            else:
                self.current_speed *= 0.95
                if abs(self.current_speed) < 1:
                    self.current_speed = 0
                self.current = random.uniform(0, 0.2)
                self.vibration = random.uniform(0, 0.3)

        elif self.device_type == "pump":
            level_change_prob = float(self.config.get('level_change_prob', 0.05))
            level_up = float(self.config.get('level_up_max', 0.005))
            level_down = float(self.config.get('level_down_max', 0.003))
            
            if random.random() < level_change_prob:
                self.level += random.uniform(0.001, level_up)
            if random.random() < level_change_prob * 0.6:
                self.level -= random.uniform(0.001, level_down)

            self.level = max(0, min(1.2, self.level))

            if self.is_running:
                pump_rate = float(self.config.get('pump_rate', 0.002))
                self.level -= pump_rate * delta_time
                self.flow_rate = 50.0 + random.uniform(-5, 5)
                self.current = 8.0 + random.uniform(-1, 1)
                self.running_hours += delta_time / 3600
            else:
                self.flow_rate = 0.0
                self.current = random.uniform(0, 0.3)

            self.level = max(0, min(1.2, self.level))

    def execute_command(self, command: str, speed: int = 0) -> Dict:
        result = {
            "device_id": self.device_id,
            "command": command,
            "success": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            if command == "start":
                self.is_running = True
                self.target_speed = speed if speed > 0 else 50
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 启动，转速: {self.target_speed}%")
                result["message"] = f"设备已启动，转速: {self.target_speed}%"
            elif command == "stop":
                self.is_running = False
                self.target_speed = 0
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 停止")
                result["message"] = "设备已停止"
            elif command == "set_speed":
                if self.is_running:
                    self.target_speed = max(0, min(100, speed))
                    print(f"[PLC] {self.device_type.upper()} {self.device_id} 调整转速: {self.target_speed}%")
                    result["message"] = f"转速已调整为: {self.target_speed}%"
                else:
                    print(f"[PLC] {self.device_type.upper()} {self.device_id} 未启动，无法调整转速")
                    result["success"] = False
                    result["message"] = "设备未启动"
            elif command == "status":
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 状态查询")
                result["message"] = "状态查询成功"
            elif command == "reset":
                self.is_running = False
                self.target_speed = 0
                self.current_speed = 0
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 重置")
                result["message"] = "设备已重置"
            else:
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 未知命令: {command}")
                result["success"] = False
                result["message"] = f"未知命令: {command}"
        except Exception as e:
            result["success"] = False
            result["message"] = f"命令执行失败: {str(e)}"
            print(f"[PLC] 命令执行错误: {e}")
        
        self.last_command_time = time.time()
        return result

    def get_status(self) -> dict:
        status = {
            "device_id": self.device_id,
            "cabin": self.cabin,
            "is_running": self.is_running,
            "timestamp": datetime.utcnow().isoformat()
        }

        if self.device_type == "fan":
            status.update({
                "speed": int(self.current_speed),
                "target_speed": self.target_speed,
                "current": round(self.current, 2),
                "vibration": round(self.vibration, 2),
                "running_hours": round(self.running_hours, 2),
                "status": "running" if self.is_running else "stopped"
            })
        elif self.device_type == "pump":
            status.update({
                "level": round(self.level, 3),
                "flow_rate": round(self.flow_rate, 2),
                "current": round(self.current, 2),
                "running_hours": round(self.running_hours, 2),
                "status": "running" if self.is_running else "stopped"
            })

        return status

    def get_telemetry(self) -> dict:
        return self.get_status()


class MQTTPLCSimulator:
    def __init__(self, broker: str = None, port: int = None):
        self.broker = broker or os.getenv("MQTT_BROKER", "localhost")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.username = os.getenv("MQTT_USERNAME", "")
        self.password = os.getenv("MQTT_PASSWORD", "")
        self.client_id = os.getenv("PLC_CLIENT_ID", "plc-simulator")
        
        self.telemetry_interval = int(os.getenv("PLC_TELEMETRY_INTERVAL", "5"))
        self.status_interval = int(os.getenv("PLC_STATUS_INTERVAL", "30"))
        self.fan_count = int(os.getenv("PLC_FAN_COUNT", "30"))
        self.pump_count = int(os.getenv("PLC_PUMP_COUNT", "50"))
        
        self.client = mqtt.Client(client_id=self.client_id)
        if self.username:
            self.client.username_pw_set(self.username, self.password)
            
        self.devices: Dict[str, PLCDevice] = {}
        self.running = False
        self._init_devices()

    def _init_devices(self):
        cabins = ["power", "water", "gas"]
        fans_per_cabin = max(1, self.fan_count // 3)
        pumps_per_cabin = max(1, self.pump_count // 3)
        
        device_config = {
            'level_change_prob': float(os.getenv('PLC_LEVEL_CHANGE_PROB', '0.05')),
            'level_up_max': float(os.getenv('PLC_LEVEL_UP_MAX', '0.005')),
            'level_down_max': float(os.getenv('PLC_LEVEL_DOWN_MAX', '0.003')),
            'pump_rate': float(os.getenv('PLC_PUMP_RATE', '0.002'))
        }

        for i in range(self.fan_count):
            device_id = f"FAN-{str(i+1).zfill(3)}"
            cabin_idx = i // fans_per_cabin
            cabin = cabins[min(cabin_idx, 2)]
            self.devices[device_id] = PLCDevice(device_id, "fan", cabin, device_config)

        for i in range(self.pump_count):
            device_id = f"PUMP-{str(i+1).zfill(3)}"
            cabin_idx = i // pumps_per_cabin
            cabin = cabins[min(cabin_idx, 2)]
            self.devices[device_id] = PLCDevice(device_id, "pump", cabin, device_config)

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] PLC模拟器连接成功，返回码: {rc}")
        if rc == 0:
            for device_id in self.devices:
                device = self.devices[device_id]
                topic = f"{device.device_type}/{device_id}/command"
                client.subscribe(topic, qos=1)
                print(f"[MQTT] 已订阅: {topic}")
            
            client.subscribe("plc/broadcast/#", qos=1)
            print("[MQTT] 已订阅: plc/broadcast/#")
        else:
            print(f"[MQTT] 连接失败，错误码: {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            print(f"\n[MQTT] 收到命令 - Topic: {topic}")
            print(f"         Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            
            if topic.startswith("plc/broadcast/"):
                self._handle_broadcast(topic, payload)
                return
            
            parts = topic.split("/")
            device_type = parts[0]
            device_id = parts[1]

            if device_id in self.devices:
                device = self.devices[device_id]
                command = payload.get("command", "")
                speed = payload.get("speed", 0)
                
                result = device.execute_command(command, speed)
                self._publish_response(device, result)
                self._publish_status(device)
            else:
                print(f"[MQTT] 未知设备: {device_id}")
        except json.JSONDecodeError:
            print(f"[MQTT] 消息格式错误: {msg.payload.decode()}")
        except Exception as e:
            print(f"[MQTT] 消息处理错误: {e}")

    def _handle_broadcast(self, topic: str, payload: dict):
        command = payload.get("command", "")
        device_type = payload.get("device_type", "")
        
        print(f"[PLC] 收到广播命令: {command}")
        
        for device_id, device in self.devices.items():
            if device_type and device.device_type != device_type:
                continue
                
            if command == "status_all":
                self._publish_status(device)
            elif command == "start_all":
                device.execute_command("start", payload.get("speed", 50))
                self._publish_status(device)
            elif command == "stop_all":
                device.execute_command("stop")
                self._publish_status(device)
            elif command == "emergency_stop":
                device.execute_command("stop")
                self._publish_status(device)

    def _publish_status(self, device: PLCDevice):
        topic = f"{device.device_type}/{device.device_id}/status"
        payload = device.get_status()
        self.client.publish(topic, json.dumps(payload), qos=1)
        print(f"[PLC] 状态已发布: {topic} -> {payload.get('status', '')}")

    def _publish_telemetry(self, device: PLCDevice):
        topic = f"{device.device_type}/{device.device_id}/telemetry"
        payload = device.get_telemetry()
        self.client.publish(topic, json.dumps(payload), qos=0)

    def _publish_response(self, device: PLCDevice, result: dict):
        topic = f"{device.device_type}/{device.device_id}/response"
        self.client.publish(topic, json.dumps(result), qos=1)
        print(f"[PLC] 响应已发布: {topic} -> {'成功' if result['success'] else '失败'}")

    def _update_loop(self):
        last_telemetry = {}
        last_status = {}

        while self.running:
            try:
                now = time.time()

                for device_id, device in self.devices.items():
                    device.update(0.1)

                    last_tel = last_telemetry.get(device_id, 0)
                    if now - last_tel >= self.telemetry_interval:
                        self._publish_telemetry(device)
                        last_telemetry[device_id] = now

                    last_stat = last_status.get(device_id, 0)
                    if now - last_stat >= self.status_interval:
                        self._publish_status(device)
                        last_status[device_id] = now

                time.sleep(0.1)
            except Exception as e:
                print(f"[PLC] 更新循环错误: {e}")
                time.sleep(1)

    def start(self):
        print("=" * 70)
        print("MQTT PLC模拟器启动")
        print(f"Broker: {self.broker}:{self.port}")
        print(f"风机数量: {self.fan_count}")
        print(f"排水泵数量: {self.pump_count}")
        print(f"遥测间隔: {self.telemetry_interval}s")
        print(f"状态间隔: {self.status_interval}s")
        print("-" * 70)
        print("MQTT Topic 说明:")
        print("  订阅命令: fan/{id}/command, pump/{id}/command")
        print("  发布状态: fan/{id}/status, pump/{id}/status")
        print("  发布遥测: fan/{id}/telemetry, pump/{id}/telemetry")
        print("  发布响应: fan/{id}/response, pump/{id}/response")
        print("  广播命令: plc/broadcast/status_all, start_all, stop_all")
        print("=" * 70)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.broker, self.port, 60)
        except Exception as e:
            print(f"[MQTT] 连接失败: {e}")
            sys.exit(1)

        self.running = True
        update_thread = threading.Thread(target=self._update_loop, daemon=True)
        update_thread.start()

        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        self.client.disconnect()
        print("\n[PLC] 模拟器已停止")

    def print_config(self):
        print("\n=== PLC模拟器配置 ===")
        print(f"Broker: {self.broker}:{self.port}")
        print(f"风机数量: {self.fan_count}")
        print(f"水泵数量: {self.pump_count}")
        print(f"遥测间隔: {self.telemetry_interval}s")
        print(f"状态间隔: {self.status_interval}s")
        print("设备列表:")
        for device_id, device in self.devices.items():
            print(f"  {device_id} ({device.device_type}, {device.cabin})")
        print("====================\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MQTT PLC模拟器 - 支持环境变量配置")
    parser.add_argument("--broker", help="MQTT Broker地址", default=None)
    parser.add_argument("--port", type=int, help="MQTT端口", default=None)
    parser.add_argument("--fan-count", type=int, help="风机数量", default=None)
    parser.add_argument("--pump-count", type=int, help="水泵数量", default=None)
    parser.add_argument("--telemetry-interval", type=int, help="遥测间隔(秒)", default=None)
    parser.add_argument("--status-interval", type=int, help="状态间隔(秒)", default=None)
    parser.add_argument("--print-config", action="store_true", help="打印配置并退出")
    args = parser.parse_args()

    if args.fan_count:
        os.environ["PLC_FAN_COUNT"] = str(args.fan_count)
    if args.pump_count:
        os.environ["PLC_PUMP_COUNT"] = str(args.pump_count)
    if args.telemetry_interval:
        os.environ["PLC_TELEMETRY_INTERVAL"] = str(args.telemetry_interval)
    if args.status_interval:
        os.environ["PLC_STATUS_INTERVAL"] = str(args.status_interval)

    simulator = MQTTPLCSimulator(broker=args.broker, port=args.port)

    if args.print_config:
        simulator.print_config()
        sys.exit(0)

    try:
        simulator.start()
    except KeyboardInterrupt:
        simulator.stop()
