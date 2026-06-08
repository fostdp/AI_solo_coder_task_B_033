import time
from typing import Tuple, Dict, Any
from datetime import datetime

from backend.config import settings


class PIDController:
    def __init__(self, kp: float, ki: float, kd: float, setpoint: float, 
                 output_min: float = 0, output_max: float = 100):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = setpoint
        self.output_min = output_min
        self.output_max = output_max
        
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None
        self.last_output = 0.0
    
    def update(self, measured_value: float, current_time: float = None) -> float:
        if current_time is None:
            current_time = time.time()
        
        if self.prev_time is None:
            dt = 1.0
        else:
            dt = max(0.1, current_time - self.prev_time)
        
        error = self.setpoint - measured_value
        
        self.integral += error * dt
        self.integral = max(-100, min(100, self.integral))
        
        derivative = (error - self.prev_error) / dt
        
        output = (self.kp * error + 
                  self.ki * self.integral + 
                  self.kd * derivative)
        
        output = max(self.output_min, min(self.output_max, output))
        
        self.prev_error = error
        self.prev_time = current_time
        self.last_output = output
        
        return output
    
    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0
        self.prev_time = None
        self.last_output = 0.0


class VentilationController:
    def __init__(self):
        self.oxygen_pid = PIDController(
            kp=settings.PID_KP,
            ki=settings.PID_KI,
            kd=settings.PID_KD,
            setpoint=20.0,
            output_min=0,
            output_max=100
        )
        self.temperature_pid = PIDController(
            kp=settings.PID_KP * 2,
            ki=settings.PID_KI,
            kd=settings.PID_KD * 2,
            setpoint=28.0,
            output_min=0,
            output_max=100
        )
        self.fan_states: Dict[str, Dict[str, Any]] = {}
    
    def calculate_control(self, oxygen: float, temperature: float, 
                         humidity: float) -> Tuple[bool, int, Dict[str, Any]]:
        current_time = time.time()
        
        oxygen_output = self.oxygen_pid.update(oxygen, current_time)
        temperature_output = self.temperature_pid.update(temperature, current_time)
        
        combined_output = max(oxygen_output, temperature_output)
        
        oxygen_deviation = abs(oxygen - 20.0)
        if oxygen_deviation > 0.5:
            combined_output += oxygen_deviation * 10
        
        if temperature > settings.TEMPERATURE_MAX - 2:
            combined_output = max(combined_output, 50)
        
        if oxygen < settings.OXYGEN_MIN:
            combined_output = max(combined_output, 80)
        elif oxygen > settings.OXYGEN_MAX:
            combined_output = max(combined_output, 60)
        
        if humidity > 85:
            combined_output = max(combined_output, 40)
        
        running = combined_output > 5
        speed = int(min(100, max(0, combined_output))) if running else 0
        
        if oxygen < 17 or temperature > 38:
            running = True
            speed = 100
        
        control_details = {
            "oxygen": oxygen,
            "temperature": temperature,
            "humidity": humidity,
            "oxygen_setpoint": self.oxygen_pid.setpoint,
            "temperature_setpoint": self.temperature_pid.setpoint,
            "oxygen_error": self.oxygen_pid.prev_error,
            "temperature_error": self.temperature_pid.prev_error,
            "oxygen_output": round(oxygen_output, 2),
            "temperature_output": round(temperature_output, 2),
            "combined_output": round(combined_output, 2),
            "running": running,
            "speed": speed,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return running, speed, control_details
    
    def update_fan_state(self, fan_id: str, running: bool, speed: int):
        self.fan_states[fan_id] = {
            "running": running,
            "speed": speed,
            "last_update": datetime.utcnow()
        }
    
    def get_fan_state(self, fan_id: str) -> Dict[str, Any]:
        return self.fan_states.get(fan_id, {"running": False, "speed": 0})
    
    def reset(self):
        self.oxygen_pid.reset()
        self.temperature_pid.reset()
        self.fan_states.clear()


ventilation_controller = VentilationController()
