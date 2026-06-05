import asyncio
import json
import random
import time
import httpx
from datetime import datetime
from typing import Dict, List


class LoRaGatewaySimulator:
    def __init__(self, api_url: str = "http://localhost:8000/api", use_batch: bool = True, batch_size: int = 50):
        self.api_url = api_url
        self.interval = 60
        self.env_sensor_count = 200
        self.manhole_count = 100
        self.device_states: Dict[str, dict] = {}
        self.use_batch = use_batch
        self.batch_size = batch_size
        self._init_device_states()

    def _init_device_states(self):
        cabins = ["power", "water", "gas"]

        for i in range(self.env_sensor_count):
            device_id = f"ENV-{str(i+1).zfill(4)}"
            cabin_idx = i // 67
            cabin = cabins[min(cabin_idx, 2)]

            base_temp = random.uniform(22, 28)
            base_humidity = random.uniform(45, 65)
            base_oxygen = random.uniform(19.5, 21.0)
            base_methane = random.uniform(0.0, 0.05)
            base_h2s = random.uniform(0.0, 3.0)

            self.device_states[device_id] = {
                "type": "env_sensor",
                "cabin": cabin,
                "base_temp": base_temp,
                "base_humidity": base_humidity,
                "base_oxygen": base_oxygen,
                "base_methane": base_methane,
                "base_h2s": base_h2s,
                "temp_variation": 0,
                "humidity_variation": 0,
                "oxygen_variation": 0,
                "methane_peak": False,
                "h2s_peak": False,
                "oxygen_drop": False,
                "rssi": random.randint(-75, -55)
            }

        for i in range(self.manhole_count):
            device_id = f"MH-{str(i+1).zfill(4)}"
            cabin_idx = i // 34
            cabin = cabins[min(cabin_idx, 2)]

            self.device_states[device_id] = {
                "type": "manhole",
                "cabin": cabin,
                "is_open": False,
                "is_legal": True,
                "battery_level": random.uniform(70, 100),
                "open_until": 0,
                "illegal_opening": False
            }

    def _generate_env_data(self, device_id: str, state: dict) -> dict:
        hour = datetime.now().hour

        state["temp_variation"] += random.uniform(-0.3, 0.3)
        state["temp_variation"] = max(-3, min(3, state["temp_variation"]))

        state["humidity_variation"] += random.uniform(-1, 1)
        state["humidity_variation"] = max(-10, min(10, state["humidity_variation"]))

        state["oxygen_variation"] += random.uniform(-0.05, 0.05)
        state["oxygen_variation"] = max(-2, min(1, state["oxygen_variation"]))

        if random.random() < 0.02:
            state["methane_peak"] = True
            state["peak_duration"] = random.randint(3, 8)
        if state.get("peak_duration", 0) > 0:
            state["peak_duration"] -= 1
            if state["peak_duration"] <= 0:
                state["methane_peak"] = False

        if random.random() < 0.02:
            state["h2s_peak"] = True
            state["h2s_duration"] = random.randint(3, 8)
        if state.get("h2s_duration", 0) > 0:
            state["h2s_duration"] -= 1
            if state["h2s_duration"] <= 0:
                state["h2s_peak"] = False

        if random.random() < 0.015:
            state["oxygen_drop"] = True
            state["drop_duration"] = random.randint(5, 12)
        if state.get("drop_duration", 0) > 0:
            state["drop_duration"] -= 1
            if state["drop_duration"] <= 0:
                state["oxygen_drop"] = False

        temp = state["base_temp"] + state["temp_variation"]
        if hour >= 10 and hour <= 16:
            temp += 2
        if hour >= 22 or hour <= 5:
            temp -= 1

        humidity = state["base_humidity"] + state["humidity_variation"]
        humidity = max(30, min(90, humidity))

        oxygen = state["base_oxygen"] + state["oxygen_variation"]
        if state["oxygen_drop"]:
            oxygen -= random.uniform(1.5, 3.0)
        oxygen = max(16, min(23, oxygen))

        if state["methane_peak"]:
            methane = random.uniform(0.8, 2.5)
        else:
            methane = max(0, state["base_methane"] + random.uniform(-0.02, 0.08))

        if state["h2s_peak"]:
            h2s = random.uniform(8, 25)
        else:
            h2s = max(0, state["base_h2s"] + random.uniform(-1, 2))

        state["rssi"] += random.randint(-3, 3)
        state["rssi"] = max(-95, min(-45, state["rssi"]))

        return {
            "device_id": device_id,
            "cabin": state["cabin"],
            "timestamp": datetime.utcnow().isoformat(),
            "temperature": round(temp, 2),
            "humidity": round(humidity, 2),
            "oxygen": round(oxygen, 2),
            "methane": round(methane, 4),
            "hydrogen_sulfide": round(h2s, 2),
            "rssi": state["rssi"]
        }

    def _generate_manhole_data(self, device_id: str, state: dict) -> dict:
        now = time.time()

        if state["open_until"] > now:
            is_open = True
        elif random.random() < 0.01:
            state["open_until"] = now + random.randint(60, 300)
            is_open = True
            if random.random() < 0.3:
                state["illegal_opening"] = True
                state["is_legal"] = False
            else:
                state["is_legal"] = True
        else:
            is_open = False
            state["is_legal"] = True

        if not is_open:
            state["illegal_opening"] = False

        state["battery_level"] -= random.uniform(0.001, 0.005)
        if state["battery_level"] < 10:
            state["battery_level"] = random.uniform(80, 100)

        return {
            "device_id": device_id,
            "cabin": state["cabin"],
            "timestamp": datetime.utcnow().isoformat(),
            "is_open": is_open,
            "is_legal": state["is_legal"],
            "battery_level": round(state["battery_level"], 2)
        }

    async def _send_data(self, endpoint: str, data: dict):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_url}/{endpoint}",
                    json=data
                )
                if response.status_code != 200:
                    print(f"[LoRa] 发送数据失败 ({endpoint}): {response.status_code} - {response.text}")
                return response.status_code == 200
        except Exception as e:
            print(f"[LoRa] 发送数据异常: {e}")
            return False

    async def _send_batch(self, endpoint: str, items: List[dict]) -> dict:
        try:
            batch_data = {
                "data": items,
                "gateway_id": "GW-001",
                "timestamp": datetime.utcnow().isoformat()
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/{endpoint}/batch",
                    json=batch_data
                )
                if response.status_code != 200:
                    print(f"[LoRa] 批量发送失败 ({endpoint}): {response.status_code} - {response.text}")
                    return {"success": False, "count": 0, "error": response.text}
                result = response.json()
                return {"success": True, "count": result.get("count", 0), "process_time_ms": result.get("process_time_ms", 0), "throughput": result.get("throughput", 0)}
        except Exception as e:
            print(f"[LoRa] 批量发送异常: {e}")
            return {"success": False, "count": 0, "error": str(e)}

    async def _send_batch_env_data(self):
        env_devices = [
            (did, state) for did, state in self.device_states.items()
            if state["type"] == "env_sensor"
        ]

        if self.use_batch:
            all_data = []
            for device_id, state in env_devices:
                data = self._generate_env_data(device_id, state)
                all_data.append(data)

            success_count = 0
            total_time = 0
            total_throughput = 0

            for i in range(0, len(all_data), self.batch_size):
                batch = all_data[i:i + self.batch_size]
                result = await self._send_batch("data/lora", batch)
                if result["success"]:
                    success_count += result["count"]
                    total_time += result["process_time_ms"]
                    total_throughput += result["throughput"]
                await asyncio.sleep(0.1)

            print(f"[LoRa] 环境传感器批量上报完成: {success_count}/{len(env_devices)} 成功, 总耗时: {total_time:.0f}ms, 吞吐: {total_throughput:.0f}条/s")
        else:
            success_count = 0
            for device_id, state in env_devices:
                data = self._generate_env_data(device_id, state)
                if await self._send_data("data/lora", data):
                    success_count += 1
                await asyncio.sleep(0.02)

            print(f"[LoRa] 环境传感器数据上报完成: {success_count}/{len(env_devices)} 成功")

    async def _send_batch_manhole_data(self):
        manhole_devices = [
            (did, state) for did, state in self.device_states.items()
            if state["type"] == "manhole"
        ]

        if self.use_batch:
            all_data = []
            for device_id, state in manhole_devices:
                data = self._generate_manhole_data(device_id, state)
                all_data.append(data)

            success_count = 0
            total_time = 0

            for i in range(0, len(all_data), self.batch_size):
                batch = all_data[i:i + self.batch_size]
                result = await self._send_batch("data/manhole", batch)
                if result["success"]:
                    success_count += result["count"]
                    total_time += result["process_time_ms"]
                await asyncio.sleep(0.1)

            print(f"[LoRa] 井盖传感器批量上报完成: {success_count}/{len(manhole_devices)} 成功, 总耗时: {total_time:.0f}ms")
        else:
            success_count = 0
            for device_id, state in manhole_devices:
                data = self._generate_manhole_data(device_id, state)
                if await self._send_data("data/manhole", data):
                    success_count += 1
                await asyncio.sleep(0.02)

            print(f"[LoRa] 井盖传感器数据上报完成: {success_count}/{len(manhole_devices)} 成功")

    async def run_once(self):
        print(f"\n[LoRa] 开始数据上报 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        start_time = time.time()

        await asyncio.gather(
            self._send_batch_env_data(),
            self._send_batch_manhole_data()
        )

        elapsed = time.time() - start_time
        print(f"[LoRa] 上报完成，耗时: {elapsed:.2f}s")

    async def run_continuous(self):
        print("=" * 60)
        print("LoRa网关模拟器启动")
        print(f"API地址: {self.api_url}")
        print(f"环境传感器: {self.env_sensor_count} 个")
        print(f"井盖传感器: {self.manhole_count} 个")
        print(f"上报间隔: {self.interval} 秒")
        print(f"批量模式: {'启用' if self.use_batch else '禁用'}")
        if self.use_batch:
            print(f"批量大小: {self.batch_size} 条/批")
        print("=" * 60)

        while True:
            try:
                await self.run_once()
            except Exception as e:
                print(f"[LoRa] 运行错误: {e}")

            sleep_time = max(0, self.interval - (time.time() % self.interval))
            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LoRa网关模拟器")
    parser.add_argument("--api-url", default="http://localhost:8000/api", help="后端API地址")
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--no-batch", action="store_true", help="禁用批量上报（逐条发送）")
    parser.add_argument("--batch-size", type=int, default=50, help="批量大小（默认50）")
    args = parser.parse_args()

    simulator = LoRaGatewaySimulator(
        api_url=args.api_url,
        use_batch=not args.no_batch,
        batch_size=args.batch_size
    )

    if args.once:
        asyncio.run(simulator.run_once())
    else:
        asyncio.run(simulator.run_continuous())
