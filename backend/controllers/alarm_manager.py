import asyncio
import httpx
from datetime import datetime, timedelta
from typing import List, Set, Dict
from config.settings import settings
from config.database import get_collection
from models.models import Alarm, AlarmType, AlarmLevel, CabinType, EnvironmentData, ManholeData
from utils.websocket import manager


class AlarmManager:
    def __init__(self):
        self.active_alarms: Dict[str, Alarm] = {}
        self.sms_cooldown: Dict[str, datetime] = {}
        self.sms_interval = timedelta(minutes=5)
        self.recent_alarm_keys: Set[str] = set()
        self.alarm_window = timedelta(seconds=30)

    def _get_alarm_key(self, device_id: str, alarm_type: str) -> str:
        return f"{device_id}:{alarm_type}"

    def _should_suppress(self, alarm_key: str) -> bool:
        return alarm_key in self.recent_alarm_keys

    async def _send_sms(self, alarm: Alarm):
        try:
            phone_numbers = ["13800138000", "13900139000"]
            message = f"[管廊告警]{alarm.level.value.upper()}: {alarm.message} 舱室:{alarm.cabin.value} 设备:{alarm.device_id} 时间:{alarm.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

            async with httpx.AsyncClient() as client:
                for phone in phone_numbers:
                    try:
                        await client.post(
                            settings.SMS_API_URL,
                            json={"phone": phone, "message": message},
                            timeout=5.0
                        )
                    except Exception as e:
                        print(f"[短信告警] 发送到 {phone} 失败: {e}")

            print(f"[短信告警] 已发送: {message}")
        except Exception as e:
            print(f"[短信告警] 发送失败: {e}")

    async def check_environment_data(self, data: EnvironmentData) -> List[Alarm]:
        alarms = []
        now = datetime.utcnow()

        if data.methane >= settings.METHANE_ALARM:
            alarm_key = self._get_alarm_key(data.device_id, AlarmType.GAS_LEVEL1)
            if not self._should_suppress(alarm_key):
                alarm = Alarm(
                    alarm_type=AlarmType.GAS_LEVEL1,
                    level=AlarmLevel.CRITICAL,
                    device_id=data.device_id,
                    cabin=data.cabin,
                    message=f"甲烷浓度超标: {data.methane}% (阈值: {settings.METHANE_ALARM}%)"
                )
                alarms.append(alarm)
                self.recent_alarm_keys.add(alarm_key)

        if data.hydrogen_sulfide >= settings.H2S_ALARM:
            alarm_key = self._get_alarm_key(data.device_id, AlarmType.GAS_LEVEL1)
            if not self._should_suppress(alarm_key):
                alarm = Alarm(
                    alarm_type=AlarmType.GAS_LEVEL1,
                    level=AlarmLevel.CRITICAL,
                    device_id=data.device_id,
                    cabin=data.cabin,
                    message=f"硫化氢浓度超标: {data.hydrogen_sulfide}ppm (阈值: {settings.H2S_ALARM}ppm)"
                )
                alarms.append(alarm)
                self.recent_alarm_keys.add(alarm_key)

        if data.oxygen <= settings.OXYGEN_DANGER:
            alarm_key = self._get_alarm_key(data.device_id, AlarmType.SUFFOCATION)
            if not self._should_suppress(alarm_key):
                alarm = Alarm(
                    alarm_type=AlarmType.SUFFOCATION,
                    level=AlarmLevel.CRITICAL,
                    device_id=data.device_id,
                    cabin=data.cabin,
                    message=f"氧气浓度过低: {data.oxygen}% (阈值: {settings.OXYGEN_DANGER}%)"
                )
                alarms.append(alarm)
                self.recent_alarm_keys.add(alarm_key)

        if data.temperature > settings.TEMP_MAX:
            alarm_key = self._get_alarm_key(data.device_id, AlarmType.TEMPERATURE)
            if not self._should_suppress(alarm_key):
                alarm = Alarm(
                    alarm_type=AlarmType.TEMPERATURE,
                    level=AlarmLevel.WARNING,
                    device_id=data.device_id,
                    cabin=data.cabin,
                    message=f"温度过高: {data.temperature}℃ (阈值: {settings.TEMP_MAX}℃)"
                )
                alarms.append(alarm)
                self.recent_alarm_keys.add(alarm_key)

        for alarm in alarms:
            await self._process_alarm(alarm)

        return alarms

    async def check_manhole_data(self, data: ManholeData) -> List[Alarm]:
        alarms = []

        if data.is_open and not data.is_legal:
            alarm_key = self._get_alarm_key(data.device_id, AlarmType.SECURITY)
            if not self._should_suppress(alarm_key):
                alarm = Alarm(
                    alarm_type=AlarmType.SECURITY,
                    level=AlarmLevel.WARNING,
                    device_id=data.device_id,
                    cabin=data.cabin,
                    message="井盖被非法开启！"
                )
                alarms.append(alarm)
                self.recent_alarm_keys.add(alarm_key)

        for alarm in alarms:
            await self._process_alarm(alarm)

        return alarms

    async def _process_alarm(self, alarm: Alarm):
        alarm_dict = alarm.dict(exclude={"id"})
        result = await get_collection("alarms").insert_one(alarm_dict)
        alarm.id = str(result.inserted_id)

        self.active_alarms[alarm.id] = alarm

        await manager.broadcast({
            "type": "alarm",
            "data": {
                "id": alarm.id,
                "alarm_type": alarm.alarm_type.value,
                "level": alarm.level.value,
                "device_id": alarm.device_id,
                "cabin": alarm.cabin.value,
                "message": alarm.message,
                "timestamp": alarm.timestamp.isoformat()
            }
        })

        if alarm.alarm_type == AlarmType.SUFFOCATION:
            alarm_key = self._get_alarm_key(alarm.device_id, alarm.alarm_type)
            last_sent = self.sms_cooldown.get(alarm_key)
            if last_sent is None or datetime.utcnow() - last_sent > self.sms_interval:
                asyncio.create_task(self._send_sms(alarm))
                self.sms_cooldown[alarm_key] = datetime.utcnow()
                print(f"[告警系统] 短信已触发 (二级窒息告警): {alarm.message}")
        else:
            print(f"[告警系统] WebSocket推送 (一级/其他告警，不发短信): {alarm.level.value} - {alarm.message}")

    async def acknowledge_alarm(self, alarm_id: str, user: str) -> bool:
        result = await get_collection("alarms").update_one(
            {"_id": alarm_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": user,
                "acknowledged_at": datetime.utcnow()
            }}
        )
        if result.modified_count > 0 and alarm_id in self.active_alarms:
            del self.active_alarms[alarm_id]
        return result.modified_count > 0

    async def cleanup_old_alarms(self):
        while True:
            await asyncio.sleep(60)
            cutoff = datetime.utcnow() - self.alarm_window
            self.recent_alarm_keys = set()
            cutoff_active = datetime.utcnow() - timedelta(hours=24)
            expired_ids = [
                aid for aid, alarm in self.active_alarms.items()
                if alarm.timestamp < cutoff_active and alarm.acknowledged
            ]
            for aid in expired_ids:
                del self.active_alarms[aid]


alarm_manager = AlarmManager()
