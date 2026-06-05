import json
import time
import random
import threading
from datetime import datetime
from typing import Dict
import paho.mqtt.client as mqtt


class PLCDevice:
    def __init__(self, device_id: str, device_type: str, cabin: str):
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
            if random.random() < 0.05:
                self.level += random.uniform(0.001, 0.005)
            if random.random() < 0.03:
                self.level -= random.uniform(0.001, 0.003)

            self.level = max(0, min(1.2, self.level))

            if self.is_running:
                self.level -= 0.002 * delta_time
                self.flow_rate = 50.0 + random.uniform(-5, 5)
                self.current = 8.0 + random.uniform(-1, 1)
                self.running_hours += delta_time / 3600
            else:
                self.flow_rate = 0.0
                self.current = random.uniform(0, 0.3)

            self.level = max(0, min(1.2, self.level))

    def execute_command(self, command: str, speed: int = 0):
        if command == "start":
            self.is_running = True
            self.target_speed = speed if speed > 0 else 50
            print(f"[PLC] {self.device_type.upper()} {self.device_id} 启动，转速: {self.target_speed}%")
        elif command == "stop":
            self.is_running = False
            self.target_speed = 0
            print(f"[PLC] {self.device_type.upper()} {self.device_id} 停止")
        elif command == "set_speed":
            if self.is_running:
                self.target_speed = speed
                print(f"[PLC] {self.device_type.upper()} {self.device_id} 调整转速: {speed}%")

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
                "running_hours": round(self.running_hours, 2)
            })
        elif self.device_type == "pump":
            status.update({
                "level": round(self.level, 3),
                "flow_rate": round(self.flow_rate, 2),
                "current": round(self.current, 2),
                "running_hours": round(self.running_hours, 2)
            })

        return status

    def get_telemetry(self) -> dict:
        return self.get_status()


class MQTTPLCSimulator:
    def __init__(self, broker: str = "localhost", port: int = 1883):
        self.broker = broker
        self.port = port
        self.client = mqtt.Client()
        self.devices: Dict[str, PLCDevice] = {}
        self.running = False
        self.telemetry_interval = 5
        self.status_interval = 30
        self._init_devices()

    def _init_devices(self):
        cabins = ["power", "water", "gas"]

        for i in range(30):
            device_id = f"FAN-{str(i+1).zfill(3)}"
            cabin_idx = i // 10
            cabin = cabins[min(cabin_idx, 2)]
            self.devices[device_id] = PLCDevice(device_id, "fan", cabin)

        for i in range(50):
            device_id = f"PUMP-{str(i+1).zfill(3)}"
            cabin_idx = i // 17
            cabin = cabins[min(cabin_idx, 2)]
            self.devices[device_id] = PLCDevice(device_id, "pump", cabin)

    def on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] PLC模拟器连接成功，返回码: {rc}")
        for device_id in self.devices:
            device = self.devices[device_id]
            client.subscribe(f"{device.device_type}/{device_id}/command")
            print(f"[MQTT] 已订阅: {device.device_type}/{device_id}/command")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            parts = topic.split("/")
            device_type = parts[0]
            device_id = parts[1]

            if device_id in self.devices:
                device = self.devices[device_id]
                command = payload.get("command", "")
                speed = payload.get("speed", 0)
                device.execute_command(command, speed)
                self._publish_status(device)
            else:
                print(f"[MQTT] 未知设备: {device_id}")
        except Exception as e:
            print(f"[MQTT] 消息处理错误: {e}")

    def _publish_status(self, device: PLCDevice):
        topic = f"{device.device_type}/{device.device_id}/status"
        payload = device.get_status()
        self.client.publish(topic, json.dumps(payload))

    def _publish_telemetry(self, device: PLCDevice):
        topic = f"{device.device_type}/{device.device_id}/telemetry"
        payload = device.get_telemetry()
        self.client.publish(topic, json.dumps(payload))

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
        print("=" * 60)
        print("MQTT PLC模拟器启动")
        print(f"Broker: {self.broker}:{self.port}")
        print(f"风机数量: 30")
        print(f"排水泵数量: 50")
        print(f"遥测间隔: {self.telemetry_interval}s")
        print(f"状态间隔: {self.status_interval}s")
        print("=" * 60)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect(self.broker, self.port, 60)

        self.running = True
        update_thread = threading.Thread(target=self._update_loop, daemon=True)
        update_thread.start()

        self.client.loop_forever()

    def stop(self):
        self.running = False
        self.client.disconnect()
        print("[PLC] 模拟器已停止")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MQTT PLC模拟器")
    parser.add_argument("--broker", default="localhost", help="MQTT Broker地址")
    parser.add_argument("--port", type=int, default=1883, help="MQTT端口")
    args = parser.parse_args()

    simulator = MQTTPLCSimulator(broker=args.broker, port=args.port)
    try:
        simulator.start()
    except KeyboardInterrupt:
        simulator.stop()
