import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import redis.asyncio as redis
import json
import math

from backend.config import settings
from backend.models.database import (
    fire_alerts_collection,
    fire_zone_status_collection,
    sensor_data_collection,
    devices_collection,
    control_commands_collection,
    fire_alert_confirmations_collection,
    heat_source_analysis_collection
)
from backend.models.schemas import (
    FireSensorData,
    FireAlert,
    FireZoneStatus,
    Location,
    HeatSourceFeature,
    WeldingDetectionResult,
    FireAlertConfirmation
)

logger = logging.getLogger(__name__)


class BayesianFireDetector:
    def __init__(self):
        self.prior_fire = 0.001
        self.prior_no_fire = 0.999

        self.p_temp_rate_high_given_fire = 0.85
        self.p_temp_rate_high_given_no_fire = 0.05

        self.p_smoke_high_given_fire = 0.90
        self.p_smoke_high_given_no_fire = 0.03

        self.p_temp_high_given_fire = 0.75
        self.p_temp_high_given_no_fire = 0.10

        self.p_correlation_high_given_fire = 0.95
        self.p_correlation_high_given_no_fire = 0.08

    def calculate_fire_probability(
        self,
        temperature: float,
        temp_rate: float,
        smoke_density: float,
        temp_smoke_correlation: float
    ) -> float:
        temp_high = temperature > 45.0
        temp_rate_high = temp_rate > settings.FIRE_TEMP_RATE_WARNING
        smoke_high = smoke_density > settings.FIRE_SMOKE_DENSITY_WARNING
        correlation_high = temp_smoke_correlation > 0.7

        likelihood_fire = 1.0
        likelihood_no_fire = 1.0

        if temp_rate_high:
            likelihood_fire *= self.p_temp_rate_high_given_fire
            likelihood_no_fire *= self.p_temp_rate_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_temp_rate_high_given_fire)
            likelihood_no_fire *= (1 - self.p_temp_rate_high_given_no_fire)

        if smoke_high:
            likelihood_fire *= self.p_smoke_high_given_fire
            likelihood_no_fire *= self.p_smoke_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_smoke_high_given_fire)
            likelihood_no_fire *= (1 - self.p_smoke_high_given_no_fire)

        if temp_high:
            likelihood_fire *= self.p_temp_high_given_fire
            likelihood_no_fire *= self.p_temp_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_temp_high_given_fire)
            likelihood_no_fire *= (1 - self.p_temp_high_given_no_fire)

        if correlation_high:
            likelihood_fire *= self.p_correlation_high_given_fire
            likelihood_no_fire *= self.p_correlation_high_given_no_fire
        else:
            likelihood_fire *= (1 - self.p_correlation_high_given_fire)
            likelihood_no_fire *= (1 - self.p_correlation_high_given_no_fire)

        posterior_fire = self.prior_fire * likelihood_fire
        posterior_no_fire = self.prior_no_fire * likelihood_no_fire

        total = posterior_fire + posterior_no_fire
        if total == 0:
            return 0.0

        return posterior_fire / total


class FireDetector:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.bayesian_detector = BayesianFireDetector()
        self.alert_cooldowns: Dict[str, datetime] = {}
        self.temperature_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.smoke_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.running = False
        self.active_fire_zones: Dict[str, Dict[str, Any]] = {}
        self.pending_confirmations: Dict[str, FireAlertConfirmation] = {}
        self.heat_source_cache: Dict[str, List[Tuple[datetime, float, float]]] = {}

    async def connect_redis(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB
        )
        logger.info("Fire Detector connected to Redis")

    async def disconnect_redis(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Fire Detector disconnected from Redis")

    def _calculate_temp_rate(self, device_id: str, current_temp: float) -> float:
        now = datetime.utcnow()

        if device_id not in self.temperature_history:
            self.temperature_history[device_id] = []

        self.temperature_history[device_id].append((now, current_temp))

        cutoff = now - timedelta(minutes=5)
        self.temperature_history[device_id] = [
            (t, v) for t, v in self.temperature_history[device_id]
            if t >= cutoff
        ]

        history = self.temperature_history[device_id]
        if len(history) < 2:
            return 0.0

        first_time, first_temp = history[0]
        time_diff = (now - first_time).total_seconds() / 60.0

        if time_diff < 0.5:
            return 0.0

        rate = (current_temp - first_temp) / time_diff
        return max(0, rate)

    def _calculate_temp_smoke_correlation(self, device_id: str) -> float:
        temp_history = self.temperature_history.get(device_id, [])
        smoke_history = self.smoke_history.get(device_id, [])

        if len(temp_history) < 3 or len(smoke_history) < 3:
            return 0.0

        n = min(len(temp_history), len(smoke_history), 10)

        temps = [t[1] for t in temp_history[-n:]]
        smokes = [s[1] for s in smoke_history[-n:]]

        if len(temps) < 2 or len(smokes) < 2:
            return 0.0

        avg_temp = sum(temps) / len(temps)
        avg_smoke = sum(smokes) / len(smokes)

        covariance = sum((t - avg_temp) * (s - avg_smoke) for t, s in zip(temps, smokes))
        variance_temp = sum((t - avg_temp) ** 2 for t in temps)
        variance_smoke = sum((s - avg_smoke) ** 2 for s in smokes)

        if variance_temp == 0 or variance_smoke == 0:
            return 0.0

        correlation = covariance / math.sqrt(variance_temp * variance_smoke)
        return max(-1, min(1, correlation))

    def _is_equipment_overheat(self, device_id: str, temperature: float, chamber: str) -> bool:
        if temperature < 60.0:
            return False

        pumps = ["pump"]
        fans = ["fan"]
        device = devices_collection.find_one({"device_id": device_id})

        if device and device.get("type") in pumps + fans:
            return temperature < 80.0

        return False

    async def process_fire_sensor_data(self, data: FireSensorData) -> Dict[str, Any]:
        device_info = await devices_collection.find_one({"device_id": data.device_id})
        if not device_info:
            return {"status": "error", "message": f"Device {data.device_id} not found"}

        chamber = device_info.get("chamber", "综合")
        distance_km = device_info.get("distance_km", 0)

        now = datetime.utcnow()
        if data.device_id not in self.smoke_history:
            self.smoke_history[data.device_id] = []
        self.smoke_history[data.device_id].append((now, data.smoke_density))

        if data.device_id not in self.heat_source_cache:
            self.heat_source_cache[data.device_id] = []
        self.heat_source_cache[data.device_id].append((now, data.temperature, data.smoke_density))

        cutoff = now - timedelta(minutes=5)
        self.smoke_history[data.device_id] = [
            (t, v) for t, v in self.smoke_history[data.device_id]
            if t >= cutoff
        ]

        heat_cutoff = now - timedelta(minutes=max(settings.FIRE_HEAT_SOURCE_DURATION_MIN, 10))
        self.heat_source_cache[data.device_id] = [
            (t, temp, smoke) for t, temp, smoke in self.heat_source_cache[data.device_id]
            if t >= heat_cutoff
        ]

        temp_rate = data.temperature_rate if data.temperature_rate is not None \
            else self._calculate_temp_rate(data.device_id, data.temperature)

        correlation = self._calculate_temp_smoke_correlation(data.device_id)

        heat_source_features = await self._extract_heat_source_features(data.device_id)
        welding_result = await self._detect_welding_operation(data.device_id, heat_source_features)

        fire_probability = self.bayesian_detector.calculate_fire_probability(
            temperature=data.temperature,
            temp_rate=temp_rate,
            smoke_density=data.smoke_density,
            temp_smoke_correlation=correlation
        )

        is_overheat = self._is_equipment_overheat(
            data.device_id, data.temperature, chamber
        )

        adjusted_fire_probability = fire_probability
        if welding_result.is_welding:
            adjusted_fire_probability *= (1.0 - welding_result.confidence * 0.8)
            logger.info(f"Welding operation detected at {data.device_id}, adjusted fire probability from {fire_probability:.3f} to {adjusted_fire_probability:.3f}")

        result = {
            "status": "success",
            "device_id": data.device_id,
            "chamber": chamber,
            "distance_km": distance_km,
            "temperature": data.temperature,
            "temp_rate": temp_rate,
            "smoke_density": data.smoke_density,
            "correlation": correlation,
            "fire_probability": fire_probability,
            "adjusted_fire_probability": adjusted_fire_probability,
            "is_equipment_overheat": is_overheat,
            "is_welding": welding_result.is_welding,
            "welding_confidence": welding_result.confidence,
            "heat_source_features": heat_source_features.dict()
        }

        if adjusted_fire_probability >= settings.FIRE_PROBABILITY_THRESHOLD and not is_overheat and not welding_result.is_welding:
            risk_level = "critical" if adjusted_fire_probability >= 0.9 else "warning"
            
            requires_confirmation = risk_level == "critical"
            
            if requires_confirmation:
                confirmation = await self._create_alert_confirmation(
                    data.device_id, chamber, distance_km, adjusted_fire_probability,
                    data.temperature, data.smoke_density, risk_level
                )
                result["confirmation"] = confirmation.dict()
                result["risk_level"] = risk_level
                result["requires_confirmation"] = True
                
                if confirmation.auto_upgraded:
                    alert_result = await self._create_fire_alert(
                        chamber, distance_km, adjusted_fire_probability,
                        data.temperature, data.smoke_density, risk_level
                    )
                    result["alert"] = alert_result
                    await self._activate_fire_response(chamber, distance_km, alert_result["alert_id"])
            else:
                alert_result = await self._create_fire_alert(
                    chamber, distance_km, adjusted_fire_probability,
                    data.temperature, data.smoke_density, risk_level
                )
                result["alert"] = alert_result
                result["risk_level"] = risk_level
                result["requires_confirmation"] = False

                await self._activate_fire_response(chamber, distance_km, alert_result["alert_id"])
        elif adjusted_fire_probability >= 0.5:
            result["risk_level"] = "attention"
        else:
            result["risk_level"] = "normal"
        
        await self._check_confirmation_timeouts()

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:fire:update",
                json.dumps({
                    "device_id": data.device_id,
                    "chamber": chamber,
                    "distance_km": distance_km,
                    "fire_probability": fire_probability,
                    "risk_level": result["risk_level"],
                    "timestamp": datetime.utcnow().isoformat()
                })
            )

        return result

    async def _create_fire_alert(
        self,
        chamber: str,
        distance_km: float,
        probability: float,
        temperature: float,
        smoke_density: float,
        risk_level: str
    ) -> Dict[str, Any]:
        zone_key = f"{chamber}_{int(distance_km)}"
        now = datetime.utcnow()

        if zone_key in self.alert_cooldowns:
            if now - self.alert_cooldowns[zone_key] < timedelta(minutes=5):
                return {"alert_id": "cooldown", "message": "告警冷却中"}

        if risk_level == "critical":
            message = f"火灾危急！{chamber} {distance_km:.1f}公里处，概率{probability:.0%}，温度{temperature:.1f}°C，烟雾{smoke_density:.1f}%"
        else:
            message = f"火灾预警：{chamber} {distance_km:.1f}公里处，概率{probability:.0%}，温度{temperature:.1f}°C，烟雾{smoke_density:.1f}%"

        alert = FireAlert(
            alert_id=f"fire_{now.strftime('%Y%m%d_%H%M%S')}",
            chamber=chamber,
            distance_km=distance_km,
            probability=probability,
            temperature=temperature,
            smoke_density=smoke_density,
            risk_level=risk_level,
            message=message,
            is_equipment_overheat=False
        )

        result = await fire_alerts_collection.insert_one(alert.model_dump(exclude={"id"}))
        self.alert_cooldowns[zone_key] = now

        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:alarm:fire",
                json.dumps({
                    "alert_id": alert.alert_id,
                    "chamber": chamber,
                    "distance_km": distance_km,
                    "probability": probability,
                    "risk_level": risk_level,
                    "message": message,
                    "timestamp": now.isoformat()
                })
            )

        return {"alert_id": alert.alert_id, "message": message}

    async def _activate_fire_response(self, chamber: str, distance_km: float, alert_id: str):
        zone_id = f"{chamber}_{int(distance_km / 1.0)}"

        self.active_fire_zones[zone_id] = {
            "chamber": chamber,
            "distance_km": distance_km,
            "alert_id": alert_id,
            "activated_at": datetime.utcnow(),
            "actions_taken": []
        }

        await self._close_fire_doors(zone_id, chamber, distance_km)
        await self._activate_extinguishers(zone_id, chamber, distance_km)
        await self._increase_ventilation(chamber)

        await fire_zone_status_collection.update_one(
            {"zone_id": zone_id},
            {"$set": {
                "chamber": chamber,
                "start_distance_km": max(0, distance_km - 0.5),
                "end_distance_km": min(settings.TUNNEL_LENGTH, distance_km + 0.5),
                "fire_door_status": "closing",
                "extinguisher_status": "activating",
                "temperature": 0,
                "smoke_density": 0,
                "last_update": datetime.utcnow()
            }},
            upsert=True
        )

    async def _close_fire_doors(self, zone_id: str, chamber: str, distance_km: float):
        fire_doors = await devices_collection.find({
            "type": "fire_door",
            "chamber": chamber,
            "distance_km": {"$gte": max(0, distance_km - 0.5), "$lte": min(settings.TUNNEL_LENGTH, distance_km + 0.5)}
        }).to_list(length=10)

        for door in fire_doors:
            command = {
                "device_id": door["device_id"],
                "command": "close",
                "parameters": {"zone_id": zone_id, "reason": "fire_response"},
                "source": "fire_detection"
            }
            await control_commands_collection.insert_one(command)

            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:control:command",
                    json.dumps(command)
                )

            if zone_id in self.active_fire_zones:
                self.active_fire_zones[zone_id]["actions_taken"].append(
                    f"关闭防火门 {door['device_id']}"
                )

        await fire_alerts_collection.update_one(
            {"alert_id": self.active_fire_zones[zone_id]["alert_id"]},
            {"$push": {"actions_taken": f"关闭 {len(fire_doors)} 道防火门"}}
        )

    async def _activate_extinguishers(self, zone_id: str, chamber: str, distance_km: float):
        extinguishers = await devices_collection.find({
            "type": "fire_extinguisher",
            "chamber": chamber,
            "distance_km": {"$gte": max(0, distance_km - 0.5), "$lte": min(settings.TUNNEL_LENGTH, distance_km + 0.5)}
        }).to_list(length=20)

        for extinguisher in extinguishers:
            command = {
                "device_id": extinguisher["device_id"],
                "command": "activate",
                "parameters": {"zone_id": zone_id, "reason": "fire_response"},
                "source": "fire_detection"
            }
            await control_commands_collection.insert_one(command)

            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:control:command",
                    json.dumps(command)
                )

            if zone_id in self.active_fire_zones:
                self.active_fire_zones[zone_id]["actions_taken"].append(
                    f"启动灭火装置 {extinguisher['device_id']}"
                )

        await fire_alerts_collection.update_one(
            {"alert_id": self.active_fire_zones[zone_id]["alert_id"]},
            {"$push": {"actions_taken": f"启动 {len(extinguishers)} 套灭火装置"}}
        )

    async def _increase_ventilation(self, chamber: str):
        from backend.services.mqtt_service import mqtt_service

        fans = await devices_collection.find({
            "type": "fan",
            "chamber": chamber
        }).to_list(length=settings.FANS_PER_CHAMBER)

        for fan in fans:
            command = {
                "device_id": fan["device_id"],
                "command": "start",
                "parameters": {"speed": 100, "reason": "fire_response"},
                "source": "fire_detection"
            }
            await control_commands_collection.insert_one(command)

            await mqtt_service.publish(
                settings.MQTT_TOPIC_CONTROL,
                json.dumps(command)
            )

    async def get_active_fire_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        alerts = await fire_alerts_collection.find(
            {"acknowledged": False}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        from backend.models.database import serialize_documents
        return serialize_documents(alerts)

    async def get_fire_zone_status(self, chamber: Optional[str] = None) -> List[Dict[str, Any]]:
        query = {}
        if chamber:
            query["chamber"] = chamber

        zones = await fire_zone_status_collection.find(query).to_list(length=50)
        from backend.models.database import serialize_documents
        return serialize_documents(zones)

    async def acknowledge_fire_alert(self, alert_id: str) -> bool:
        result = await fire_alerts_collection.update_one(
            {"alert_id": alert_id},
            {"$set": {"acknowledged": True}}
        )
        return result.modified_count > 0

    async def deactivate_fire_zone(self, zone_id: str) -> bool:
        if zone_id in self.active_fire_zones:
            del self.active_fire_zones[zone_id]

        result = await fire_zone_status_collection.update_one(
            {"zone_id": zone_id},
            {"$set": {
                "fire_door_status": "normal",
                "extinguisher_status": "normal"
            }}
        )
        return result.modified_count > 0

    async def _extract_heat_source_features(self, device_id: str) -> HeatSourceFeature:
        history = self.heat_source_cache.get(device_id, [])
        
        if len(history) < 3:
            return HeatSourceFeature(
                device_id=device_id,
                temperature_max=0.0,
                temperature_min=0.0,
                temperature_mean=0.0,
                temperature_std=0.0,
                temp_distribution_score=0.0,
                duration_minutes=0.0,
                smoke_mean=0.0,
                temp_smoke_correlation=0.0,
                fluctuation_frequency=0.0,
                is_periodic=False
            )
        
        temps = [h[1] for h in history]
        smokes = [h[2] for h in history]
        times = [h[0] for h in history]
        
        temp_max = max(temps)
        temp_min = min(temps)
        temp_mean = sum(temps) / len(temps)
        temp_std = math.sqrt(sum((t - temp_mean) ** 2 for t in temps) / len(temps))
        
        temp_range = temp_max - temp_min
        temp_distribution_score = min(1.0, temp_range / settings.FIRE_TEMP_DISTRIBUTION_THRESHOLD)
        
        duration_minutes = abs((times[-1] - times[0]).total_seconds()) / 60.0
        
        smoke_mean = sum(smokes) / len(smokes)
        
        if len(temps) >= 3 and len(smokes) >= 3:
            avg_temp = temp_mean
            avg_smoke = smoke_mean
            covariance = sum((t - avg_temp) * (s - avg_smoke) for t, s in zip(temps, smokes))
            var_temp = sum((t - avg_temp) ** 2 for t in temps)
            var_smoke = sum((s - avg_smoke) ** 2 for s in smokes)
            if var_temp > 0 and var_smoke > 0:
                correlation = covariance / math.sqrt(var_temp * var_smoke)
            else:
                correlation = 0.0
        else:
            correlation = 0.0
        
        fluctuation_count = 0
        diffs = []
        for i in range(1, len(temps)):
            diffs.append(temps[i] - temps[i-1])
        
        for i in range(1, len(diffs)):
            if diffs[i] * diffs[i-1] < 0:
                window_size = min(3, i, len(diffs) - i - 1)
                if window_size >= 1:
                    left_max = max(temps[i-window_size:i+1])
                    left_min = min(temps[i-window_size:i+1])
                    right_max = max(temps[i:i+window_size+2])
                    right_min = min(temps[i:i+window_size+2])
                    peak_to_peak = max(left_max, right_max) - min(left_min, right_min)
                else:
                    peak_to_peak = abs(temps[i+1] - temps[i-1])
                
                if peak_to_peak > settings.FIRE_WELDING_TEMP_FLUCTUATION / 4:
                    fluctuation_count += 1
        
        temp_range = temp_max - temp_min
        has_significant_range = temp_range > settings.FIRE_WELDING_TEMP_FLUCTUATION
        
        has_significant_std = temp_std > settings.FIRE_WELDING_TEMP_FLUCTUATION / 2
        
        if duration_minutes > 0:
            fluctuation_frequency = fluctuation_count / duration_minutes
        else:
            fluctuation_frequency = 0.0
        
        is_periodic = (fluctuation_frequency >= (0.5 / settings.FIRE_WELDING_CYCLE_SECONDS) or 
                      (has_significant_range and has_significant_std and len(temps) >= 10))
        
        return HeatSourceFeature(
            device_id=device_id,
            temperature_max=temp_max,
            temperature_min=temp_min,
            temperature_mean=temp_mean,
            temperature_std=temp_std,
            temp_distribution_score=temp_distribution_score,
            duration_minutes=duration_minutes,
            smoke_mean=smoke_mean,
            temp_smoke_correlation=max(-1.0, min(1.0, correlation)),
            fluctuation_frequency=fluctuation_frequency,
            is_periodic=is_periodic
        )

    async def _detect_welding_operation(
        self,
        device_id: str,
        features: HeatSourceFeature
    ) -> WeldingDetectionResult:
        reasons = []
        scores = []
        
        if features.temperature_std >= settings.FIRE_WELDING_TEMP_FLUCTUATION:
            temp_fluctuation_score = min(1.0, features.temperature_std / (settings.FIRE_WELDING_TEMP_FLUCTUATION * 2))
            scores.append(temp_fluctuation_score)
            reasons.append(f"温度波动明显 (std={features.temperature_std:.1f}°C)")
        else:
            temp_fluctuation_score = 0.0
            scores.append(0.0)
        
        if features.is_periodic:
            periodicity_score = min(1.0, features.fluctuation_frequency / (120.0 / settings.FIRE_WELDING_CYCLE_SECONDS))
            scores.append(periodicity_score)
            reasons.append(f"温度周期性波动 (freq={features.fluctuation_frequency:.1f}/min)")
        else:
            periodicity_score = 0.0
            scores.append(0.0)
        
        if features.smoke_mean < settings.FIRE_WELDING_SMOKE_THRESHOLD and features.temperature_mean > 40.0:
            smoke_level_score = 1.0 - min(1.0, features.smoke_mean / settings.FIRE_WELDING_SMOKE_THRESHOLD)
            scores.append(smoke_level_score)
            reasons.append(f"高温低烟特征 (烟={features.smoke_mean:.1f}%)")
        else:
            smoke_level_score = 0.0
            scores.append(0.0)
        
        if features.temp_smoke_correlation < 0.3 and features.temperature_mean > 40.0:
            correlation_score = 1.0 - abs(features.temp_smoke_correlation)
            scores.append(correlation_score)
            reasons.append(f"温烟低相关性 (corr={features.temp_smoke_correlation:.2f})")
        else:
            correlation_score = 0.0
            scores.append(0.0)
        
        if features.duration_minutes >= settings.FIRE_HEAT_SOURCE_DURATION_MIN and features.duration_minutes < 120:
            duration_score = 0.8
            scores.append(duration_score)
            reasons.append(f"热源持续时间符合焊接特征 ({features.duration_minutes:.0f}分钟)")
        else:
            duration_score = 0.0
            scores.append(0.0)
        
        if scores:
            confidence = sum(scores) / len(scores)
        else:
            confidence = 0.0
        
        is_welding = confidence >= 0.6
        
        result = WeldingDetectionResult(
            device_id=device_id,
            is_welding=is_welding,
            confidence=confidence,
            temp_fluctuation_score=temp_fluctuation_score,
            periodicity_score=periodicity_score,
            smoke_level_score=smoke_level_score,
            reasons=reasons
        )
        
        if is_welding:
            await heat_source_analysis_collection.insert_one({
                "device_id": device_id,
                "analysis_type": "welding_detection",
                "is_welding": True,
                "confidence": confidence,
                "features": features.dict(),
                "result": result.dict(),
                "timestamp": datetime.utcnow()
            })
        
        return result

    async def _create_alert_confirmation(
        self,
        device_id: str,
        chamber: str,
        distance_km: float,
        probability: float,
        temperature: float,
        smoke_density: float,
        risk_level: str
    ) -> FireAlertConfirmation:
        confirmation_id = f"confirm_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{device_id}"
        
        confirmation = FireAlertConfirmation(
            confirmation_id=confirmation_id,
            alert_id="pending",
            chamber=chamber,
            distance_km=distance_km,
            risk_level=risk_level,
            requires_confirmation=True,
            timeout_seconds=settings.FIRE_HUMAN_CONFIRM_TIMEOUT
        )
        
        self.pending_confirmations[confirmation_id] = confirmation
        
        await fire_alert_confirmations_collection.insert_one(confirmation.model_dump(exclude={"id"}))
        
        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:fire:confirmation_required",
                json.dumps({
                    "confirmation_id": confirmation_id,
                    "chamber": chamber,
                    "distance_km": distance_km,
                    "probability": probability,
                    "temperature": temperature,
                    "smoke_density": smoke_density,
                    "risk_level": risk_level,
                    "timeout_seconds": settings.FIRE_HUMAN_CONFIRM_TIMEOUT,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
        
        logger.info(f"Created fire alert confirmation: {confirmation_id}, timeout: {settings.FIRE_HUMAN_CONFIRM_TIMEOUT}s")
        
        return confirmation

    async def confirm_fire_alert(
        self,
        confirmation_id: str,
        confirmed: bool,
        confirmed_by: str,
        confirmation_result: str
    ) -> bool:
        confirmation = self.pending_confirmations.get(confirmation_id)
        if not confirmation:
            confirmation_doc = await fire_alert_confirmations_collection.find_one({"confirmation_id": confirmation_id})
            if not confirmation_doc:
                return False
            confirmation = FireAlertConfirmation(**confirmation_doc)
        
        confirmation.confirmed = True
        confirmation.confirmed_by = confirmed_by
        confirmation.confirmed_at = datetime.utcnow()
        confirmation.confirmation_result = confirmation_result
        
        await fire_alert_confirmations_collection.update_one(
            {"confirmation_id": confirmation_id},
            {"$set": {
                "confirmed": True,
                "confirmed_by": confirmed_by,
                "confirmed_at": confirmation.confirmed_at,
                "confirmation_result": confirmation_result
            }}
        )
        
        if confirmation_id in self.pending_confirmations:
            del self.pending_confirmations[confirmation_id]
        
        if self.redis_client:
            await self.redis_client.publish(
                "tunnel:fire:confirmation_result",
                json.dumps({
                    "confirmation_id": confirmation_id,
                    "confirmed": confirmed,
                    "confirmed_by": confirmed_by,
                    "confirmation_result": confirmation_result,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
        
        if confirmed and confirmation_result == "fire_confirmed":
            alert_result = await self._create_fire_alert(
                confirmation.chamber,
                confirmation.distance_km,
                0.95,
                0.0,
                0.0,
                confirmation.risk_level
            )
            await self._activate_fire_response(
                confirmation.chamber,
                confirmation.distance_km,
                alert_result["alert_id"]
            )
        elif not confirmed or confirmation_result == "false_alarm":
            zone_id = f"{confirmation.chamber}_{int(confirmation.distance_km / 1.0)}"
            await self.deactivate_fire_zone(zone_id)
        
        logger.info(f"Fire alert confirmation {confirmation_id} processed: {confirmation_result} by {confirmed_by}")
        return True

    async def _check_confirmation_timeouts(self) -> None:
        now = datetime.utcnow()
        timeout_confirmations = []
        
        for conf_id, confirmation in list(self.pending_confirmations.items()):
            elapsed = (now - confirmation.created_at).total_seconds()
            if elapsed >= confirmation.timeout_seconds:
                timeout_confirmations.append((conf_id, confirmation))
        
        for conf_id, confirmation in timeout_confirmations:
            confirmation.confirmed = True
            confirmation.auto_upgraded = True
            confirmation.confirmed_at = now
            confirmation.confirmation_result = "timeout_auto_upgrade"
            
            await fire_alert_confirmations_collection.update_one(
                {"confirmation_id": conf_id},
                {"$set": {
                    "confirmed": True,
                    "auto_upgraded": True,
                    "confirmed_at": now,
                    "confirmation_result": "timeout_auto_upgrade"
                }}
            )
            
            del self.pending_confirmations[conf_id]
            
            alert_result = await self._create_fire_alert(
                confirmation.chamber,
                confirmation.distance_km,
                0.9,
                0.0,
                0.0,
                confirmation.risk_level
            )
            await self._activate_fire_response(
                confirmation.chamber,
                confirmation.distance_km,
                alert_result["alert_id"]
            )
            
            if self.redis_client:
                await self.redis_client.publish(
                    "tunnel:fire:confirmation_timeout",
                    json.dumps({
                        "confirmation_id": conf_id,
                        "chamber": confirmation.chamber,
                        "distance_km": confirmation.distance_km,
                        "risk_level": confirmation.risk_level,
                        "alert_id": alert_result["alert_id"],
                        "timestamp": now.isoformat()
                    })
                )
            
            logger.warning(f"Fire alert confirmation {conf_id} timed out after {confirmation.timeout_seconds}s, auto-upgraded to alert")

    async def _auto_dismiss_alert(self, alert_id: str, reason: str) -> bool:
        result = await fire_alerts_collection.update_one(
            {"alert_id": alert_id},
            {"$set": {
                "acknowledged": True,
                "dismissed": True,
                "dismiss_reason": reason,
                "dismissed_at": datetime.utcnow()
            }}
        )
        
        if result.modified_count > 0 and self.redis_client:
            await self.redis_client.publish(
                "tunnel:fire:alert_dismissed",
                json.dumps({
                    "alert_id": alert_id,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat()
                })
            )
        
        return result.modified_count > 0

    async def get_pending_confirmations(self) -> List[Dict[str, Any]]:
        pending = list(self.pending_confirmations.values())
        return [c.dict() for c in pending]

    async def start_listener(self):
        self.running = True
        logger.info("Fire Detector listener started")

        while self.running:
            try:
                if not self.redis_client:
                    await self.connect_redis()

                pubsub = self.redis_client.pubsub()
                await pubsub.subscribe("tunnel:sensor:fire")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            fire_data = FireSensorData(**data)
                            await self.process_fire_sensor_data(fire_data)
                        except Exception as e:
                            logger.error(f"Error processing fire sensor data: {e}")

            except Exception as e:
                logger.error(f"Fire Detector listener error: {e}")
                await asyncio.sleep(5)

        logger.info("Fire Detector listener stopped")


fire_detector = FireDetector()
