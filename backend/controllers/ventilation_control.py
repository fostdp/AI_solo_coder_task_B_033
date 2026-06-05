import time
from typing import Tuple, Dict
from config.settings import settings
from models.models import CabinType


class FuzzyVentilationController:
    def __init__(self):
        self.oxygen_target = (settings.OXYGEN_MIN + settings.OXYGEN_MAX) / 2
        self.temp_max = settings.TEMP_MAX
        self.fan_states: Dict[str, dict] = {}

    def _fuzzify_oxygen(self, oxygen: float) -> str:
        if oxygen < 17.0:
            return "very_low"
        elif oxygen < 18.5:
            return "low"
        elif oxygen < 19.5:
            return "slightly_low"
        elif oxygen <= 21.0:
            return "normal"
        else:
            return "high"

    def _fuzzify_temperature(self, temp: float) -> str:
        if temp < 25:
            return "low"
        elif temp < 30:
            return "medium"
        elif temp < 35:
            return "high"
        else:
            return "very_high"

    def _fuzzify_humidity(self, humidity: float) -> str:
        if humidity < 40:
            return "low"
        elif humidity < 60:
            return "normal"
        elif humidity < 80:
            return "high"
        else:
            return "very_high"

    def _infer(self, oxy_level: str, temp_level: str, hum_level: str) -> Tuple[bool, int]:
        rule_table = {
            ("very_low", "very_high", "very_high"): (True, 100),
            ("very_low", "very_high", "high"): (True, 100),
            ("very_low", "very_high", "normal"): (True, 90),
            ("very_low", "very_high", "low"): (True, 85),
            ("very_low", "high", "very_high"): (True, 95),
            ("very_low", "high", "high"): (True, 90),
            ("very_low", "high", "normal"): (True, 85),
            ("very_low", "high", "low"): (True, 80),
            ("very_low", "medium", "very_high"): (True, 80),
            ("very_low", "medium", "high"): (True, 75),
            ("very_low", "medium", "normal"): (True, 70),
            ("very_low", "medium", "low"): (True, 65),
            ("very_low", "low", "very_high"): (True, 70),
            ("very_low", "low", "high"): (True, 65),
            ("very_low", "low", "normal"): (True, 60),
            ("very_low", "low", "low"): (True, 55),
            ("low", "very_high", "very_high"): (True, 90),
            ("low", "very_high", "high"): (True, 85),
            ("low", "very_high", "normal"): (True, 80),
            ("low", "very_high", "low"): (True, 75),
            ("low", "high", "very_high"): (True, 85),
            ("low", "high", "high"): (True, 80),
            ("low", "high", "normal"): (True, 75),
            ("low", "high", "low"): (True, 70),
            ("low", "medium", "very_high"): (True, 70),
            ("low", "medium", "high"): (True, 65),
            ("low", "medium", "normal"): (True, 60),
            ("low", "medium", "low"): (True, 55),
            ("low", "low", "very_high"): (True, 60),
            ("low", "low", "high"): (True, 55),
            ("low", "low", "normal"): (True, 50),
            ("low", "low", "low"): (False, 0),
            ("slightly_low", "very_high", "very_high"): (True, 75),
            ("slightly_low", "very_high", "high"): (True, 70),
            ("slightly_low", "very_high", "normal"): (True, 65),
            ("slightly_low", "very_high", "low"): (True, 60),
            ("slightly_low", "high", "very_high"): (True, 70),
            ("slightly_low", "high", "high"): (True, 65),
            ("slightly_low", "high", "normal"): (True, 60),
            ("slightly_low", "high", "low"): (True, 55),
            ("slightly_low", "medium", "very_high"): (True, 55),
            ("slightly_low", "medium", "high"): (True, 50),
            ("slightly_low", "medium", "normal"): (False, 0),
            ("slightly_low", "medium", "low"): (False, 0),
            ("slightly_low", "low", "very_high"): (True, 50),
            ("slightly_low", "low", "high"): (False, 0),
            ("slightly_low", "low", "normal"): (False, 0),
            ("slightly_low", "low", "low"): (False, 0),
            ("normal", "very_high", "very_high"): (True, 60),
            ("normal", "very_high", "high"): (True, 55),
            ("normal", "very_high", "normal"): (True, 50),
            ("normal", "very_high", "low"): (False, 0),
            ("normal", "high", "very_high"): (True, 55),
            ("normal", "high", "high"): (True, 50),
            ("normal", "high", "normal"): (False, 0),
            ("normal", "high", "low"): (False, 0),
            ("normal", "medium", "very_high"): (False, 0),
            ("normal", "medium", "high"): (False, 0),
            ("normal", "medium", "normal"): (False, 0),
            ("normal", "medium", "low"): (False, 0),
            ("normal", "low", "very_high"): (False, 0),
            ("normal", "low", "high"): (False, 0),
            ("normal", "low", "normal"): (False, 0),
            ("normal", "low", "low"): (False, 0),
            ("high", "very_high", "very_high"): (True, 40),
            ("high", "very_high", "high"): (True, 35),
            ("high", "very_high", "normal"): (True, 30),
            ("high", "very_high", "low"): (False, 0),
            ("high", "high", "very_high"): (True, 30),
            ("high", "high", "high"): (False, 0),
            ("high", "high", "normal"): (False, 0),
            ("high", "high", "low"): (False, 0),
        }

        key = (oxy_level, temp_level, hum_level)
        if key in rule_table:
            return rule_table[key]

        if temp_level in ["very_high", "high"]:
            return (True, 40)
        return (False, 0)

    def calculate(self, oxygen: float, temperature: float, humidity: float) -> Tuple[bool, int]:
        oxy_level = self._fuzzify_oxygen(oxygen)
        temp_level = self._fuzzify_temperature(temperature)
        hum_level = self._fuzzify_humidity(humidity)
        return self._infer(oxy_level, temp_level, hum_level)

    def update_fan_state(self, device_id: str, is_running: bool, speed: int):
        self.fan_states[device_id] = {
            "is_running": is_running,
            "speed": speed,
            "last_update": time.time()
        }

    def get_fan_state(self, device_id: str) -> dict:
        return self.fan_states.get(device_id, {"is_running": False, "speed": 0})


class PIDVentilationController:
    def __init__(self):
        self.oxygen_target = (settings.OXYGEN_MIN + settings.OXYGEN_MAX) / 2
        self.temp_target = 28.0
        self.temp_max = settings.TEMP_MAX
        self.kp = 2.5
        self.ki = 0.1
        self.kd = 0.5
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = time.time()

    def calculate(self, oxygen: float, temperature: float, humidity: float) -> Tuple[bool, int]:
        current_time = time.time()
        dt = current_time - self.prev_time
        if dt <= 0:
            dt = 1.0

        oxy_error = self.oxygen_target - oxygen
        temp_excess = max(0, temperature - self.temp_max)

        combined_error = oxy_error * 0.7 + temp_excess * 0.3

        self.integral += combined_error * dt
        self.integral = max(-50, min(50, self.integral))

        derivative = (combined_error - self.prev_error) / dt

        output = self.kp * combined_error + self.ki * self.integral + self.kd * derivative

        self.prev_error = combined_error
        self.prev_time = current_time

        if output > 5:
            speed = int(min(100, output * 2 + 30))
            return (True, speed)
        elif temperature > self.temp_max:
            return (True, 50)
        else:
            self.integral = max(0, self.integral)
            return (False, 0)


ventilation_controller = FuzzyVentilationController()
