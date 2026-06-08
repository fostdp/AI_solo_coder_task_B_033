import time
from typing import Tuple, Dict, Any
from datetime import datetime
from collections import deque

from backend.config import settings


class PumpController:
    def __init__(self):
        self.pump_states: Dict[str, Dict[str, Any]] = {}
        self.level_history: Dict[str, deque] = {}
        self.auto_mode: Dict[str, bool] = {}
    
    def _init_pump(self, pump_id: str):
        if pump_id not in self.pump_states:
            self.pump_states[pump_id] = {
                "running": False,
                "last_start_time": None,
                "last_stop_time": None,
                "start_count": 0,
                "run_duration": 0.0
            }
            self.level_history[pump_id] = deque(maxlen=60)
            self.auto_mode[pump_id] = True
    
    def _get_average_level(self, pump_id: str) -> float:
        history = self.level_history.get(pump_id, deque())
        if not history:
            return 0.0
        return sum(history) / len(history)
    
    def calculate_control(self, pump_id: str, level: float) -> Tuple[bool, Dict[str, Any]]:
        self._init_pump(pump_id)
        
        self.level_history[pump_id].append(level)
        avg_level = self._get_average_level(pump_id)
        
        state = self.pump_states[pump_id]
        current_time = time.time()
        
        should_run = False
        reason = "normal"
        
        if not self.auto_mode[pump_id]:
            control_details = {
                "pump_id": pump_id,
                "level": level,
                "avg_level": round(avg_level, 2),
                "running": state["running"],
                "auto_mode": False,
                "reason": "manual_mode",
                "timestamp": datetime.utcnow().isoformat()
            }
            return state["running"], control_details
        
        if state["running"]:
            if avg_level <= settings.PUMP_LEVEL_LOW:
                if state["last_start_time"] is not None:
                    run_duration = current_time - state["last_start_time"]
                    if run_duration >= 30:
                        should_run = False
                        reason = "level_normal"
                    else:
                        should_run = True
                        reason = "min_run_time"
                else:
                    should_run = False
                    reason = "level_normal"
            else:
                should_run = True
                reason = "pumping"
        else:
            if avg_level >= settings.PUMP_LEVEL_HIGH:
                should_run = True
                reason = "level_high"
            elif avg_level >= settings.PUMP_LEVEL_HIGH * 0.9:
                if state["last_stop_time"] is not None:
                    time_since_stop = current_time - state["last_stop_time"]
                    if time_since_stop > settings.PUMP_DELAY:
                        should_run = True
                        reason = "preemptive"
                    else:
                        should_run = False
                        reason = "delay_wait"
                else:
                    should_run = True
                    reason = "level_high"
            else:
                should_run = False
                reason = "normal"
        
        control_changed = should_run != state["running"]
        
        if control_changed:
            if should_run:
                state["running"] = True
                state["last_start_time"] = current_time
                state["start_count"] += 1
            else:
                state["running"] = False
                state["last_stop_time"] = current_time
                if state["last_start_time"] is not None:
                    state["run_duration"] += current_time - state["last_start_time"]
        
        control_details = {
            "pump_id": pump_id,
            "level": level,
            "avg_level": round(avg_level, 2),
            "level_high": settings.PUMP_LEVEL_HIGH,
            "level_low": settings.PUMP_LEVEL_LOW,
            "running": state["running"],
            "auto_mode": self.auto_mode[pump_id],
            "reason": reason,
            "control_changed": control_changed,
            "start_count": state["start_count"],
            "total_run_duration": round(state.get("run_duration", 0.0), 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return state["running"], control_details
    
    def set_manual_mode(self, pump_id: str, running: bool):
        self._init_pump(pump_id)
        self.auto_mode[pump_id] = False
        self.pump_states[pump_id]["running"] = running
        if running:
            self.pump_states[pump_id]["last_start_time"] = time.time()
        else:
            self.pump_states[pump_id]["last_stop_time"] = time.time()
    
    def set_auto_mode(self, pump_id: str):
        self._init_pump(pump_id)
        self.auto_mode[pump_id] = True
    
    def get_pump_state(self, pump_id: str) -> Dict[str, Any]:
        self._init_pump(pump_id)
        return self.pump_states[pump_id].copy()
    
    def reset(self):
        self.pump_states.clear()
        self.level_history.clear()
        self.auto_mode.clear()


pump_controller = PumpController()
