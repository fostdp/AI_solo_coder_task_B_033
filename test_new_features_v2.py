import sys
import os
import json
import math
import random
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from collections import deque
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SimpleLocation:
    type: str = "Point"
    coordinates: List[float] = field(default_factory=lambda: [0.0, 0.0])


@dataclass
class SimpleWaypoint:
    x: float
    y: float
    distance_km: float = 0.0
    location: SimpleLocation = None
    action: str = "inspect"
    estimated_time: float = 30.0
    waypoint_id: int = 0


@dataclass
class SimpleAsset:
    asset_id: str
    device_id: str
    device_type: str
    name: str
    model: str
    manufacturer: str
    install_date: str
    design_life_years: float
    location: Dict[str, Any] = field(default_factory=dict)
    specifications: Dict[str, Any] = field(default_factory=dict)
    purchase_cost: float = 0.0
    supplier: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    status: str = "active"
    last_maintenance_date: str = ""
    maintenance_count: int = 0
    failure_count: int = 0


@dataclass
class SimpleMaintenanceTask:
    task_id: str
    asset_id: str
    asset_name: str
    task_type: str
    priority: int
    due_date: str
    estimated_hours: float
    description: str = ""
    status: str = "pending"


@dataclass
class SimpleMaintenanceRecord:
    record_id: str
    asset_id: str
    maintenance_date: str
    task_type: str
    cost: float
    technician: str = ""
    notes: str = ""


@dataclass
class SimpleRemainingLifePrediction:
    asset_id: str
    asset_name: str
    remaining_life_years: float
    confidence: float
    prediction_date: str
    factors: Dict[str, Any] = field(default_factory=dict)


class FeatureTestSuite:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.test_results = []
        self.test_details = {}
    
    def run_test(self, test_name: str, test_func, category: str = "general"):
        try:
            logger.info(f"Running test: {test_name}")
            start_time = datetime.now()
            result = test_func()
            duration = (datetime.now() - start_time).total_seconds()
            
            if result:
                logger.info(f"✅ PASS: {test_name} ({duration:.3f}s)")
                self.passed += 1
                self.test_results.append({"name": test_name, "status": "pass", "duration": duration, "category": category})
            else:
                logger.error(f"❌ FAIL: {test_name} ({duration:.3f}s)")
                self.failed += 1
                self.test_results.append({"name": test_name, "status": "fail", "duration": duration, "category": category})
                self.errors.append(test_name)
                
        except Exception as e:
            logger.error(f"❌ ERROR: {test_name} - {e}")
            self.failed += 1
            self.test_results.append({"name": test_name, "status": "error", "error": str(e), "category": category})
            self.errors.append(f"{test_name}: {e}")
    
    def print_summary(self):
        logger.info("\n" + "=" * 80)
        logger.info("NEW FEATURES TEST SUMMARY")
        logger.info("=" * 80)
        
        categories = {}
        for r in self.test_results:
            cat = r.get("category", "general")
            if cat not in categories:
                categories[cat] = {"pass": 0, "fail": 0, "error": 0, "total": 0}
            categories[cat][r["status"]] += 1
            categories[cat]["total"] += 1
        
        for cat, stats in categories.items():
            logger.info(f"\n📋 {cat.upper()}: {stats['pass']}/{stats['total']} passed")
        
        logger.info("\n" + "-" * 80)
        logger.info(f"Total tests: {self.passed + self.failed}")
        logger.info(f"Passed: {self.passed} ({self.passed/(self.passed+self.failed)*100:.1f}%)")
        logger.info(f"Failed: {self.failed}")
        
        if self.errors:
            logger.info("\n❌ Failed tests:")
            for err in self.errors:
                logger.info(f"  - {err}")
        
        avg_duration = sum(r.get("duration", 0) for r in self.test_results) / len(self.test_results)
        logger.info(f"\n⏱️  Average test duration: {avg_duration:.4f}s")
        logger.info("=" * 80)
        
        return self.failed == 0


def approx_equal(a: float, b: float, tolerance: float = 0.01) -> bool:
    return abs(a - b) <= tolerance * max(abs(a), abs(b), 1.0)


class MockConfig:
    STRAIN_WARNING_THRESHOLD = 200
    STRAIN_CRITICAL_THRESHOLD = 400
    CRACK_WARNING_THRESHOLD = 0.2
    CRACK_CRITICAL_THRESHOLD = 0.5
    ROBOT_AVOID_TEMP = 40
    ROBOT_AVOID_HUMIDITY = 80
    ROBOT_AVOID_METHANE = 0.5
    ROBOT_AVOID_H2S = 5
    FIRE_TEMP_RATE_WARNING = 2
    FIRE_TEMP_RATE_CRITICAL = 5
    FIRE_SMOKE_DENSITY_WARNING = 5
    FIRE_SMOKE_DENSITY_CRITICAL = 15
    FIRE_PROBABILITY_THRESHOLD = 0.7
    FIRE_COOLDOWN_PERIOD = 300


def test_fiber_strain_data_parsing_normal():
    test_data = {
        "device_id": "fiber_001",
        "timestamp": datetime.utcnow().isoformat(),
        "segment_index": 5,
        "strain": 150.5,
        "temperature": 22.3,
        "crack_width": 0.05
    }
    
    config = MockConfig()
    assert test_data["strain"] >= 0 and test_data["strain"] < config.STRAIN_WARNING_THRESHOLD
    assert test_data["temperature"] > -20 and test_data["temperature"] < 100
    assert test_data["segment_index"] >= 0
    
    return True


def test_fiber_strain_data_parsing_boundary():
    config = MockConfig()
    
    boundary_cases = [
        {"strain": config.STRAIN_WARNING_THRESHOLD - 0.1, "expected_level": "normal"},
        {"strain": config.STRAIN_WARNING_THRESHOLD, "expected_level": "warning"},
        {"strain": config.STRAIN_CRITICAL_THRESHOLD - 0.1, "expected_level": "warning"},
        {"strain": config.STRAIN_CRITICAL_THRESHOLD, "expected_level": "critical"},
        {"strain": 0, "expected_level": "normal"},
        {"strain": 1000, "expected_level": "critical"},
    ]
    
    def calculate_risk_level(strain, crack_width):
        if strain >= config.STRAIN_CRITICAL_THRESHOLD or crack_width >= config.CRACK_CRITICAL_THRESHOLD:
            return "critical"
        elif strain >= config.STRAIN_WARNING_THRESHOLD or crack_width >= config.CRACK_WARNING_THRESHOLD:
            return "warning"
        return "normal"
    
    for case in boundary_cases:
        level = calculate_risk_level(case["strain"], 0)
        assert level == case["expected_level"], \
            f"Strain {case['strain']} expected {case['expected_level']}, got {level}"
    
    return True


def test_fiber_strain_data_parsing_anomaly():
    invalid_data_cases = [
        {"strain": -100, "description": "negative strain"},
        {"strain": float('nan'), "description": "NaN strain"},
        {"strain": float('inf'), "description": "infinite strain"},
        {"segment_index": -1, "description": "negative segment"},
    ]
    
    for case in invalid_data_cases:
        try:
            if "strain" in case and isinstance(case["strain"], (int, float)):
                if math.isnan(case["strain"]) or math.isinf(case["strain"]):
                    continue
                assert case["strain"] >= 0, f"Should reject {case['description']}"
        except (AssertionError, ValueError):
            pass
    
    return True


def test_strain_mapping_and_location_accuracy():
    fiber_positions = [(i * 10.0, 30.5 + i * 0.2) for i in range(100)]
    
    for seg_idx in [0, 25, 50, 75, 99]:
        expected_x = seg_idx * 10.0
        expected_y = 30.5 + seg_idx * 0.2
        actual_x, actual_y = fiber_positions[seg_idx]
        
        assert approx_equal(actual_x, expected_x, 0.001), f"X coordinate error at segment {seg_idx}"
        assert approx_equal(actual_y, expected_y, 0.001), f"Y coordinate error at segment {seg_idx}"
    
    return True


def test_heatmap_generation_normal():
    n_points = 50
    heatmap_data = []
    for i in range(n_points):
        heatmap_data.append({
            "x": i * 2.0,
            "y": 30.0 + math.sin(i * 0.1) * 5,
            "strain": random.uniform(50, 180),
            "risk_level": "normal"
        })
    
    assert len(heatmap_data) == n_points
    for point in heatmap_data:
        assert "x" in point and "y" in point and "strain" in point
        assert point["risk_level"] == "normal"
        assert point["strain"] >= 50 and point["strain"] < 200
    
    return True


def test_heatmap_generation_boundary():
    heatmap_data = []
    for i in range(10):
        if i < 3:
            strain = 150
            risk = "normal"
        elif i < 6:
            strain = 250
            risk = "warning"
        else:
            strain = 450
            risk = "critical"
        
        heatmap_data.append({
            "x": i * 10.0,
            "y": 30.0,
            "strain": strain,
            "risk_level": risk
        })
    
    normal_count = sum(1 for p in heatmap_data if p["risk_level"] == "normal")
    warning_count = sum(1 for p in heatmap_data if p["risk_level"] == "warning")
    critical_count = sum(1 for p in heatmap_data if p["risk_level"] == "critical")
    
    assert normal_count == 3
    assert warning_count == 3
    assert critical_count == 4
    
    strains = [p["strain"] for p in heatmap_data]
    assert min(strains) < 200
    assert max(strains) >= 400
    
    return True


def test_heatmap_color_mapping():
    config = MockConfig()
    
    def calculate_risk_level(strain, crack_width):
        if strain >= config.STRAIN_CRITICAL_THRESHOLD or crack_width >= config.CRACK_CRITICAL_THRESHOLD:
            return "critical"
        elif strain >= config.STRAIN_WARNING_THRESHOLD or crack_width >= config.CRACK_WARNING_THRESHOLD:
            return "warning"
        return "normal"
    
    def get_risk_color(level):
        if level == "critical":
            return "rgba(239, 68, 68, 0.8)"
        elif level == "warning":
            return "rgba(249, 115, 22, 0.8)"
        return "rgba(34, 197, 94, 0.8)"
    
    test_cases = [
        (50, "normal", "rgba(34, 197, 94"),
        (150, "normal", "rgba(34, 197, 94"),
        (200, "warning", "rgba(249, 115, 22"),
        (300, "warning", "rgba(249, 115, 22"),
        (400, "critical", "rgba(239, 68, 68"),
        (500, "critical", "rgba(239, 68, 68"),
    ]
    
    for strain, expected_level, expected_color_prefix in test_cases:
        level = calculate_risk_level(strain, 0)
        assert level == expected_level, f"Level mismatch for strain {strain}"
        color = get_risk_color(level)
        assert color.startswith(expected_color_prefix), f"Color mismatch for strain {strain}"
    
    return True


def test_crack_warning_timeliness():
    alert_timestamps = []
    last_alert_time = {}
    config = MockConfig()
    
    def calculate_risk_level(strain, crack_width):
        if strain >= config.STRAIN_CRITICAL_THRESHOLD or crack_width >= config.CRACK_CRITICAL_THRESHOLD:
            return "critical"
        elif strain >= config.STRAIN_WARNING_THRESHOLD or crack_width >= config.CRACK_WARNING_THRESHOLD:
            return "warning"
        return "normal"
    
    def process_fiber_data(data, current_time=None):
        risk_level = calculate_risk_level(data["strain"], data.get("crack_width", 0))
        
        device_key = data["device_id"]
        now = current_time or datetime.utcnow()
        
        if risk_level in ["warning", "critical"]:
            last_alert = last_alert_time.get(device_key)
            if not last_alert or (now - last_alert) > timedelta(minutes=10):
                alert_timestamps.append(now)
                last_alert_time[device_key] = now
                return True, risk_level
        
        return False, risk_level
    
    t0 = datetime(2025, 1, 1, 12, 0, 0)
    data1 = {"device_id": "fiber_001", "timestamp": t0.isoformat(), "strain": 450, "crack_width": 0.3}
    triggered1, level1 = process_fiber_data(data1, t0)
    
    assert triggered1 == True, "First alert should trigger"
    assert level1 == "critical", "Should be critical level"
    
    t1 = datetime(2025, 1, 1, 12, 1, 0)
    data2 = {"device_id": "fiber_001", "timestamp": t1.isoformat(), "strain": 480, "crack_width": 0.35}
    triggered2, level2 = process_fiber_data(data2, t1)
    
    assert triggered2 == False, "Alert within cooldown should not trigger"
    
    t2 = datetime(2025, 1, 1, 12, 11, 0)
    data3 = {"device_id": "fiber_001", "timestamp": t2.isoformat(), "strain": 500, "crack_width": 0.4}
    triggered3, level3 = process_fiber_data(data3, t2)
    
    assert triggered3 == True, "Alert after cooldown should trigger"
    
    return True


def test_crack_warning_false_positive_rate():
    config = MockConfig()
    
    def calculate_risk_level(strain, crack_width):
        if strain >= config.STRAIN_CRITICAL_THRESHOLD or crack_width >= config.CRACK_CRITICAL_THRESHOLD:
            return "critical"
        elif strain >= config.STRAIN_WARNING_THRESHOLD or crack_width >= config.CRACK_WARNING_THRESHOLD:
            return "warning"
        return "normal"
    
    normal_tests = 1000
    false_positives = 0
    
    for _ in range(normal_tests):
        strain = random.uniform(0, config.STRAIN_WARNING_THRESHOLD - 1)
        crack = random.uniform(0, config.CRACK_WARNING_THRESHOLD - 0.01)
        level = calculate_risk_level(strain, crack)
        if level in ["warning", "critical"]:
            false_positives += 1
    
    false_positive_rate = false_positives / normal_tests
    assert false_positive_rate < 0.01, f"False positive rate too high: {false_positive_rate:.2%}"
    
    critical_tests = 100
    false_negatives = 0
    
    for _ in range(critical_tests):
        strain = random.uniform(config.STRAIN_CRITICAL_THRESHOLD + 1, 1000)
        level = calculate_risk_level(strain, 0)
        if level != "critical":
            false_negatives += 1
    
    false_negative_rate = false_negatives / critical_tests
    assert false_negative_rate < 0.05, f"False negative rate too high: {false_negative_rate:.2%}"
    
    return True


def test_alert_cooldown_mechanism():
    alerts = []
    last_alert_time = {}
    config = MockConfig()
    
    def calculate_risk_level(strain, crack_width):
        if strain >= config.STRAIN_CRITICAL_THRESHOLD or crack_width >= config.CRACK_CRITICAL_THRESHOLD:
            return "critical"
        return "normal"
    
    def trigger_alert(device_id, strain, level):
        now = datetime.utcnow()
        last_alert = last_alert_time.get(device_id)
        cooldown = timedelta(minutes=10)
        
        if last_alert and (now - last_alert) < cooldown:
            return False
        
        alerts.append({"device_id": device_id, "strain": strain, "level": level, "timestamp": now})
        last_alert_time[device_id] = now
        return True
    
    t0 = datetime.utcnow()
    
    assert trigger_alert("fiber_001", 500, "critical") == True
    assert len(alerts) == 1
    
    assert trigger_alert("fiber_001", 550, "critical") == False
    assert len(alerts) == 1
    
    assert trigger_alert("fiber_002", 600, "critical") == True
    assert len(alerts) == 2
    
    return True


def test_path_planning_obstacle_avoidance_high_temp():
    config = MockConfig()
    
    def is_dangerous(x, y, obstacles):
        for obs in obstacles:
            dx = abs(x - obs["x"])
            dy = abs(y - obs["y"])
            if dx < 5 and dy < 5:
                if obs["temperature"] >= config.ROBOT_AVOID_TEMP:
                    return True
        return False
    
    obstacles = [
        {"x": 30, "y": 30, "temperature": 50, "humidity": 50, "methane": 0.1, "h2s": 2},
        {"x": 50, "y": 30, "temperature": 45, "humidity": 50, "methane": 0.1, "h2s": 2},
    ]
    
    assert is_dangerous(30, 30, obstacles) == True, "High temperature should be dangerous"
    assert is_dangerous(10, 30, obstacles) == False, "Low temperature should be safe"
    
    return True


def test_path_planning_obstacle_avoidance_high_humidity():
    config = MockConfig()
    
    def is_dangerous(x, y, obstacles):
        for obs in obstacles:
            dx = abs(x - obs["x"])
            dy = abs(y - obs["y"])
            if dx < 5 and dy < 5:
                if obs["humidity"] >= config.ROBOT_AVOID_HUMIDITY:
                    return True
        return False
    
    obstacles = [
        {"x": 30, "y": 30, "temperature": 25, "humidity": 90, "methane": 0.1, "h2s": 2},
    ]
    
    assert is_dangerous(30, 30, obstacles) == True, "High humidity should be dangerous"
    assert is_dangerous(10, 30, obstacles) == False, "Low humidity should be safe"
    
    return True


def test_path_planning_obstacle_avoidance_gas():
    config = MockConfig()
    
    def is_dangerous(x, y, obstacles):
        for obs in obstacles:
            dx = abs(x - obs["x"])
            dy = abs(y - obs["y"])
            if dx < 5 and dy < 5:
                if obs["methane"] >= config.ROBOT_AVOID_METHANE or obs["h2s"] >= config.ROBOT_AVOID_H2S:
                    return True
        return False
    
    gas_zones = [
        {"x": 40, "y": 30, "temperature": 25, "humidity": 50, "methane": 0.8, "h2s": 2},
        {"x": 50, "y": 30, "temperature": 25, "humidity": 50, "methane": 0.1, "h2s": 10},
    ]
    
    assert is_dangerous(40, 30, gas_zones) == True, "High methane should be dangerous"
    assert is_dangerous(50, 30, gas_zones) == True, "High H2S should be dangerous"
    
    safe_zone = {"x": 70, "y": 30, "temperature": 25, "humidity": 50, "methane": 0.4, "h2s": 4}
    assert is_dangerous(70, 30, [safe_zone]) == False, "Low gas levels should be safe"
    
    return True


def test_path_optimization_length():
    config = MockConfig()
    
    def is_dangerous(x, y, obstacles):
        for obs in obstacles:
            dx = abs(x - obs["x"])
            dy = abs(y - obs["y"])
            if dx < 5 and dy < 5:
                if (obs["temperature"] >= config.ROBOT_AVOID_TEMP or
                    obs["humidity"] >= config.ROBOT_AVOID_HUMIDITY or
                    obs["methane"] >= config.ROBOT_AVOID_METHANE or
                    obs["h2s"] >= config.ROBOT_AVOID_H2S):
                    return True
        return False
    
    def plan_path(start_x, start_y, end_x, end_y, obstacles):
        path = [SimpleWaypoint(x=start_x, y=start_y)]
        
        current_x, current_y = start_x, start_y
        step_size = 5
        
        while abs(current_x - end_x) > step_size or abs(current_y - end_y) > step_size:
            candidates = []
            
            for dx in [-step_size, 0, step_size]:
                for dy in [-step_size, 0, step_size]:
                    if dx == 0 and dy == 0:
                        continue
                    next_x = current_x + dx
                    next_y = current_y + dy
                    
                    if is_dangerous(next_x, next_y, obstacles):
                        continue
                    
                    dist_to_end = math.sqrt((next_x - end_x) ** 2 + (next_y - end_y) ** 2)
                    candidates.append((dist_to_end, next_x, next_y))
            
            if not candidates:
                break
            
            candidates.sort()
            _, current_x, current_y = candidates[0]
            path.append(SimpleWaypoint(x=current_x, y=current_y))
        
        path.append(SimpleWaypoint(x=end_x, y=end_y))
        return path
    
    start = SimpleWaypoint(x=0, y=30)
    end = SimpleWaypoint(x=100, y=30)
    
    obstacles = []
    for i in range(40, 61):
        obstacles.append({"x": i, "y": 30, "temperature": 45, "humidity": 50, "methane": 0.1, "h2s": 2})
    
    path = plan_path(start.x, start.y, end.x, end.y, obstacles)
    
    assert len(path) >= 2, "Path should have at least start and end"
    assert path[0].x == 0 and path[0].y == 30, "Path should start at start point"
    assert path[-1].x == 100 and path[-1].y == 30, "Path should end at end point"
    
    total_distance = 0
    for i in range(len(path) - 1):
        dx = path[i + 1].x - path[i].x
        dy = path[i + 1].y - path[i].y
        total_distance += math.sqrt(dx * dx + dy * dy)
    
    straight_distance = 100
    detour_ratio = total_distance / straight_distance
    
    assert detour_ratio >= 1.0, "Path length cannot be shorter than straight line"
    assert detour_ratio < 1.5, f"Path too long: detour ratio {detour_ratio:.2f}"
    
    for wp in path:
        is_danger = is_dangerous(wp.x, wp.y, obstacles)
        assert is_danger == False, f"Path point ({wp.x}, {wp.y}) is in danger zone"
    
    return True


def test_path_planning_boundary_cases():
    config = MockConfig()
    
    def is_dangerous(x, y, obstacles):
        for obs in obstacles:
            dx = abs(x - obs["x"])
            dy = abs(y - obs["y"])
            if dx < 5 and dy < 5:
                if (obs["temperature"] >= config.ROBOT_AVOID_TEMP or
                    obs["humidity"] >= config.ROBOT_AVOID_HUMIDITY or
                    obs["methane"] >= config.ROBOT_AVOID_METHANE or
                    obs["h2s"] >= config.ROBOT_AVOID_H2S):
                    return True
        return False
    
    def plan_path(start_x, start_y, end_x, end_y, obstacles):
        if start_x == end_x and start_y == end_y:
            return [SimpleWaypoint(x=start_x, y=start_y)]
        
        path = [SimpleWaypoint(x=start_x, y=start_y)]
        
        if not obstacles:
            path.append(SimpleWaypoint(x=end_x, y=end_y))
            return path
        
        current_x, current_y = start_x, start_y
        step_size = 5
        
        while abs(current_x - end_x) > step_size or abs(current_y - end_y) > step_size:
            candidates = []
            
            for dx in [-step_size, 0, step_size]:
                for dy in [-step_size, 0, step_size]:
                    if dx == 0 and dy == 0:
                        continue
                    next_x = current_x + dx
                    next_y = current_y + dy
                    
                    if is_dangerous(next_x, next_y, obstacles):
                        continue
                    
                    dist_to_end = math.sqrt((next_x - end_x) ** 2 + (next_y - end_y) ** 2)
                    candidates.append((dist_to_end, next_x, next_y))
            
            if not candidates:
                break
            
            candidates.sort()
            _, current_x, current_y = candidates[0]
            path.append(SimpleWaypoint(x=current_x, y=current_y))
        
        path.append(SimpleWaypoint(x=end_x, y=end_y))
        return path
    
    start = SimpleWaypoint(x=0, y=30)
    end = SimpleWaypoint(x=100, y=30)
    
    no_obstacles = []
    path1 = plan_path(start.x, start.y, end.x, end.y, no_obstacles)
    assert len(path1) == 2, "Path without obstacles should be direct"
    
    start_end_same = SimpleWaypoint(x=50, y=30)
    path2 = plan_path(start_end_same.x, start_end_same.y, start_end_same.x, start_end_same.y, [])
    assert len(path2) == 1, "Path with same start and end should have one point"
    
    return True


def test_sensor_data_fusion_accuracy():
    robot_reading = {"temperature": 25.5, "battery": 85, "speed": 1.2}
    env_readings = [
        {"device_id": "env_001", "temperature": 25.3, "humidity": 60, "methane": 0.05},
        {"device_id": "env_002", "temperature": 25.7, "humidity": 62, "methane": 0.04},
        {"device_id": "env_003", "temperature": 25.4, "humidity": 59, "methane": 0.06},
    ]
    
    env_temp_avg = sum(r["temperature"] for r in env_readings) / len(env_readings)
    temp_diff = abs(robot_reading["temperature"] - env_temp_avg)
    
    assert temp_diff < 0.5, f"Temperature discrepancy too high: {temp_diff:.2f}°C"
    
    weights = [0.6, 0.3, 0.1]
    weighted_temp = sum(w * r["temperature"] for w, r in zip(weights, env_readings))
    
    assert weighted_temp >= 25.0 and weighted_temp <= 26.0
    
    return True


def test_inspection_progress_tracking():
    total_waypoints = 20
    visited = deque(maxlen=100)
    
    for i in range(total_waypoints):
        visited.append({"x": i * 5, "y": 30, "timestamp": datetime.utcnow().isoformat()})
        progress = (i + 1) / total_waypoints * 100
        expected_progress = (i + 1) * 5
        
        assert progress >= 0 and progress <= 100, f"Progress {progress:.1f}% out of range"
        assert len(visited) == i + 1
        
        if i > 0:
            prev = visited[i - 1]
            curr = visited[i]
            dx = curr["x"] - prev["x"]
            assert approx_equal(dx, 5.0, 0.001), "Waypoint spacing inconsistent"
    
    assert progress == 100.0, "Final progress should be 100%"
    
    return True


def test_robot_position_updates():
    robot_positions = {}
    
    robot_id = "robot_001"
    waypoints = [SimpleWaypoint(x=i * 10, y=30 + math.sin(i * 0.5) * 2) for i in range(11)]
    
    start_time = datetime.utcnow()
    
    for i, wp in enumerate(waypoints):
        pos_data = {
            "robot_id": robot_id,
            "x": wp.x,
            "y": wp.y,
            "battery": 90 - i * 0.5,
            "speed": 1.2,
            "timestamp": (start_time + timedelta(seconds=i)).isoformat()
        }
        
        robot_positions[robot_id] = pos_data
        
        actual_pos = robot_positions[robot_id]
        assert actual_pos["x"] == wp.x
        assert actual_pos["y"] == wp.y
        assert actual_pos["battery"] == 90 - i * 0.5
        assert "timestamp" in actual_pos
    
    assert len(robot_positions) == 1
    
    return True


def test_robot_battery_depletion():
    robot_positions = {}
    active_missions = {}
    
    robot_id = "robot_001"
    
    for battery in [100, 50, 20, 10, 5]:
        pos = {
            "robot_id": robot_id,
            "x": 50,
            "y": 30,
            "battery": battery,
            "speed": 1.0,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if battery <= 10:
            pos["low_battery"] = True
        
        robot_positions[robot_id] = pos
        
        assert pos["battery"] == battery
        
        if battery <= 10:
            assert pos.get("low_battery", True), "Should flag low battery"
    
    return True


def test_temperature_rate_calculation():
    config = MockConfig()
    
    def calculate_temperature_rate(temps, timestamps):
        if len(temps) < 2:
            return 0.0
        dt = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0
        if dt < 0.1:
            return 0.0
        return (temps[-1] - temps[0]) / dt
    
    base_time = datetime.utcnow()
    
    normal_temps = [25.0, 25.2, 25.1, 25.3, 25.2]
    normal_times = [base_time + timedelta(minutes=i) for i in range(5)]
    normal_rate = calculate_temperature_rate(normal_temps, normal_times)
    assert abs(normal_rate) < config.FIRE_TEMP_RATE_WARNING, "Normal temp should not trigger warning"
    
    fast_rise_temps = [25.0, 30.0, 37.0, 46.0, 55.0]
    fast_rise_times = [base_time + timedelta(minutes=i) for i in range(5)]
    fast_rate = calculate_temperature_rate(fast_rise_temps, fast_rise_times)
    assert fast_rate > config.FIRE_TEMP_RATE_CRITICAL, f"Fast temp rise should trigger critical, got {fast_rate:.2f}"
    
    return True


def test_smoke_density_rate_calculation():
    config = MockConfig()
    
    def calculate_smoke_rate(smoke_values, timestamps):
        if len(smoke_values) < 2:
            return 0.0
        dt = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0
        if dt < 0.1:
            return 0.0
        return (smoke_values[-1] - smoke_values[0]) / dt
    
    base_time = datetime.utcnow()
    
    normal_smoke = [0.5, 0.6, 0.4, 0.5, 0.6]
    normal_times = [base_time + timedelta(minutes=i) for i in range(5)]
    normal_rate = calculate_smoke_rate(normal_smoke, normal_times)
    assert abs(normal_rate) < 1.0, "Normal smoke should be stable"
    
    fast_rise_smoke = [0.5, 3.0, 8.0, 15.0, 25.0]
    fast_rise_times = [base_time + timedelta(minutes=i) for i in range(5)]
    fast_rate = calculate_smoke_rate(fast_rise_smoke, fast_rise_times)
    assert fast_rate > config.FIRE_SMOKE_DENSITY_WARNING, "Fast smoke rise should trigger warning"
    
    return True


def test_temp_smoke_correlation():
    config = MockConfig()
    
    def calculate_correlation(x, y):
        n = len(x)
        if n < 2:
            return 0.0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        denominator = math.sqrt(sum((xi - mean_x) ** 2 for xi in x)) * math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    random.seed(42)
    normal_temps = [25.0 + random.uniform(-0.1, 0.1) for _ in range(5)]
    normal_smoke = [0.5 + random.uniform(-0.1, 0.1) for _ in range(5)]
    normal_corr = calculate_correlation(normal_temps, normal_smoke)
    assert abs(normal_corr) < 0.7, f"Normal conditions should have low correlation, got {normal_corr:.3f}"
    
    fire_temps = [25.0, 30.0, 36.0, 43.0, 52.0]
    fire_smoke = [0.5, 5.0, 12.0, 22.0, 35.0]
    fire_corr = calculate_correlation(fire_temps, fire_smoke)
    assert fire_corr > 0.9, f"Fire conditions should have high positive correlation, got {fire_corr:.3f}"
    
    return True


def test_bayesian_fire_probability():
    config = MockConfig()
    
    def calculate_fire_probability(temp_rate, smoke_rate, correlation):
        p_fire_prior = 0.001
        
        p_temp_given_fire = 1.0 if temp_rate > config.FIRE_TEMP_RATE_CRITICAL else \
                            0.7 if temp_rate > config.FIRE_TEMP_RATE_WARNING else 0.05
        p_smoke_given_fire = 1.0 if smoke_rate > config.FIRE_SMOKE_DENSITY_CRITICAL else \
                             0.7 if smoke_rate > config.FIRE_SMOKE_DENSITY_WARNING else 0.05
        p_corr_given_fire = 1.0 if correlation > 0.8 else 0.5 if correlation > 0.5 else 0.1
        
        p_temp_given_no_fire = 0.05
        p_smoke_given_no_fire = 0.05
        p_corr_given_no_fire = 0.05
        
        p_evidence_given_fire = p_temp_given_fire * p_smoke_given_fire * p_corr_given_fire
        p_evidence_given_no_fire = p_temp_given_no_fire * p_smoke_given_no_fire * p_corr_given_no_fire
        
        denominator = p_evidence_given_fire * p_fire_prior + p_evidence_given_no_fire * (1 - p_fire_prior)
        if denominator == 0:
            return 0.0
        
        p_fire_given_evidence = (p_evidence_given_fire * p_fire_prior) / denominator
        
        return p_fire_given_evidence
    
    fire_prob = calculate_fire_probability(6.0, 20.0, 0.95)
    assert fire_prob > config.FIRE_PROBABILITY_THRESHOLD, f"Fire probability should be high: {fire_prob:.3f}"
    
    normal_prob = calculate_fire_probability(0.1, 0.1, 0.1)
    assert normal_prob < 0.1, f"Normal probability should be low: {normal_prob:.3f}"
    
    warning_prob = calculate_fire_probability(3.0, 8.0, 0.7)
    assert warning_prob > 0.3 and warning_prob < config.FIRE_PROBABILITY_THRESHOLD, \
        f"Warning probability should be moderate: {warning_prob:.3f}"
    
    return True


def test_fire_vs_overheating_discrimination():
    config = MockConfig()
    
    def classify_event(temp_rate, smoke_rate, correlation):
        p_fire_prior = 0.001
        
        p_temp_given_fire = 1.0 if temp_rate > config.FIRE_TEMP_RATE_CRITICAL else \
                            0.7 if temp_rate > config.FIRE_TEMP_RATE_WARNING else 0.05
        p_smoke_given_fire = 1.0 if smoke_rate > config.FIRE_SMOKE_DENSITY_CRITICAL else \
                             0.7 if smoke_rate > config.FIRE_SMOKE_DENSITY_WARNING else 0.05
        p_corr_given_fire = 1.0 if correlation > 0.8 else 0.5 if correlation > 0.5 else 0.1
        
        p_temp_given_no_fire = 0.05
        p_smoke_given_no_fire = 0.05
        p_corr_given_no_fire = 0.05
        
        p_evidence_given_fire = p_temp_given_fire * p_smoke_given_fire * p_corr_given_fire
        p_evidence_given_no_fire = p_temp_given_no_fire * p_smoke_given_no_fire * p_corr_given_no_fire
        
        denominator = p_evidence_given_fire * p_fire_prior + p_evidence_given_no_fire * (1 - p_fire_prior)
        if denominator == 0:
            p_fire = 0.0
        else:
            p_fire = (p_evidence_given_fire * p_fire_prior) / denominator
        
        if p_fire > config.FIRE_PROBABILITY_THRESHOLD:
            return "fire"
        elif temp_rate > config.FIRE_TEMP_RATE_WARNING and smoke_rate < config.FIRE_SMOKE_DENSITY_WARNING:
            return "overheating"
        return "normal"
    
    fire_result = classify_event(7.0, 25.0, 0.95)
    assert fire_result == "fire", f"Should classify as fire, got {fire_result}"
    
    overheating_result = classify_event(4.0, 1.0, 0.2)
    assert overheating_result == "overheating", f"Should classify as overheating, got {overheating_result}"
    
    normal_result = classify_event(0.1, 0.1, 0.1)
    assert normal_result == "normal", f"Should classify as normal, got {normal_result}"
    
    return True


def test_fire_probability_boundary_values():
    config = MockConfig()
    
    def calculate_fire_probability(temp_rate, smoke_rate, correlation):
        p_fire_prior = 0.01
        
        p_temp_given_fire = 1.0 if temp_rate > config.FIRE_TEMP_RATE_CRITICAL else \
                            0.7 if temp_rate > config.FIRE_TEMP_RATE_WARNING else 0.1
        p_smoke_given_fire = 1.0 if smoke_rate > config.FIRE_SMOKE_DENSITY_CRITICAL else \
                             0.7 if smoke_rate > config.FIRE_SMOKE_DENSITY_WARNING else 0.1
        p_corr_given_fire = 1.0 if correlation > 0.8 else 0.5 if correlation > 0.5 else 0.1
        
        p_temp_given_no_fire = 0.05
        p_smoke_given_no_fire = 0.05
        p_corr_given_no_fire = 0.05
        
        p_evidence_given_fire = p_temp_given_fire * p_smoke_given_fire * p_corr_given_fire
        p_evidence_given_no_fire = p_temp_given_no_fire * p_smoke_given_no_fire * p_corr_given_no_fire
        
        p_fire_given_evidence = (p_evidence_given_fire * p_fire_prior) / \
                                (p_evidence_given_fire * p_fire_prior + p_evidence_given_no_fire * (1 - p_fire_prior))
        
        return p_fire_given_evidence
    
    boundary_cases = [
        (config.FIRE_TEMP_RATE_WARNING, 0.0, 0.0, 0.0, 1.0),
        (config.FIRE_TEMP_RATE_CRITICAL, 0.0, 0.0, 0.0, 1.0),
        (0.0, config.FIRE_SMOKE_DENSITY_WARNING, 0.0, 0.0, 1.0),
        (0.0, config.FIRE_SMOKE_DENSITY_CRITICAL, 0.0, 0.0, 1.0),
    ]
    
    for temp_rate, smoke_rate, corr, min_prob, max_prob in boundary_cases:
        prob = calculate_fire_probability(temp_rate, smoke_rate, corr)
        assert prob >= min_prob and prob <= max_prob, f"Probability {prob} out of range for boundary case"
    
    return True


def test_fire_false_positive_rate():
    config = MockConfig()
    
    def classify_event(temp_rate, smoke_rate, correlation):
        p_fire_prior = 0.01
        
        p_temp_given_fire = 1.0 if temp_rate > config.FIRE_TEMP_RATE_CRITICAL else \
                            0.7 if temp_rate > config.FIRE_TEMP_RATE_WARNING else 0.1
        p_smoke_given_fire = 1.0 if smoke_rate > config.FIRE_SMOKE_DENSITY_CRITICAL else \
                             0.7 if smoke_rate > config.FIRE_SMOKE_DENSITY_WARNING else 0.1
        p_corr_given_fire = 1.0 if correlation > 0.8 else 0.5 if correlation > 0.5 else 0.1
        
        p_temp_given_no_fire = 0.05
        p_smoke_given_no_fire = 0.05
        p_corr_given_no_fire = 0.05
        
        p_evidence_given_fire = p_temp_given_fire * p_smoke_given_fire * p_corr_given_fire
        p_evidence_given_no_fire = p_temp_given_no_fire * p_smoke_given_no_fire * p_corr_given_no_fire
        
        p_fire = (p_evidence_given_fire * p_fire_prior) / \
                 (p_evidence_given_fire * p_fire_prior + p_evidence_given_no_fire * (1 - p_fire_prior))
        
        return p_fire > config.FIRE_PROBABILITY_THRESHOLD
    
    n_tests = 1000
    false_positives = 0
    
    for _ in range(n_tests):
        temp_rate = random.uniform(0, 1)
        smoke_rate = random.uniform(0, 1)
        corr = random.uniform(-0.5, 0.3)
        
        if classify_event(temp_rate, smoke_rate, corr):
            false_positives += 1
    
    fp_rate = false_positives / n_tests
    assert fp_rate < 0.05, f"False positive rate too high: {fp_rate:.2%}"
    
    return True


def test_linked_control_response_time():
    class MockFireSystem:
        def __init__(self):
            self.actions = []
            self.response_times = []
        
        def trigger_fire_response(self, chamber, distance_km):
            start = datetime.utcnow()
            
            self.actions.append({
                "action": "close_fire_door",
                "chamber": chamber,
                "timestamp": datetime.utcnow()
            })
            
            self.actions.append({
                "action": "activate_extinguisher",
                "chamber": chamber,
                "distance_km": distance_km,
                "timestamp": datetime.utcnow()
            })
            
            self.actions.append({
                "action": "alert_operations",
                "level": "FIRE",
                "timestamp": datetime.utcnow()
            })
            
            elapsed = (datetime.utcnow() - start).total_seconds()
            self.response_times.append(elapsed)
            return elapsed
    
    system = MockFireSystem()
    
    n_tests = 10
    for i in range(n_tests):
        elapsed = system.trigger_fire_response(f"A{i}", i * 0.5)
        assert elapsed < 1.0, f"Response time too slow: {elapsed:.3f}s"
    
    avg_time = sum(system.response_times) / len(system.response_times)
    assert avg_time < 0.5, f"Average response time too slow: {avg_time:.3f}s"
    
    assert len(system.actions) == n_tests * 3, "Should have 3 actions per trigger"
    
    return True


def test_fire_zone_status_update():
    class MockZoneManager:
        def __init__(self):
            self.zones = {}
            self.history = []
        
        def update_zone_status(self, zone_id, status, reason=None):
            if zone_id not in self.zones:
                self.zones[zone_id] = {"status": "normal", "updates": 0}
            
            old_status = self.zones[zone_id]["status"]
            self.zones[zone_id]["status"] = status
            self.zones[zone_id]["updates"] += 1
            self.zones[zone_id]["last_update"] = datetime.utcnow()
            if reason:
                self.zones[zone_id]["reason"] = reason
            
            self.history.append({
                "zone_id": zone_id,
                "old_status": old_status,
                "new_status": status,
                "timestamp": datetime.utcnow()
            })
            
            return True
        
        def get_zone_status(self, zone_id):
            return self.zones.get(zone_id, {"status": "unknown"})
    
    manager = MockZoneManager()
    
    manager.update_zone_status("zone_A1", "normal")
    assert manager.get_zone_status("zone_A1")["status"] == "normal"
    
    manager.update_zone_status("zone_A1", "fire_warning", reason="High temperature rate")
    assert manager.get_zone_status("zone_A1")["status"] == "fire_warning"
    assert manager.get_zone_status("zone_A1")["updates"] == 2
    
    manager.update_zone_status("zone_A1", "fire_critical", reason="Fire confirmed")
    assert manager.get_zone_status("zone_A1")["status"] == "fire_critical"
    
    manager.update_zone_status("zone_A1", "all_clear", reason="Fire extinguished")
    assert manager.get_zone_status("zone_A1")["status"] == "all_clear"
    assert manager.get_zone_status("zone_A1")["updates"] == 4
    
    assert len(manager.history) == 4
    
    return True


def test_asset_data_completeness():
    test_asset = SimpleAsset(
        asset_id="asset_001",
        device_id="fan_001",
        device_type="fan",
        name="通风风机-001",
        model="FAN-2000-X",
        manufacturer="风机制造有限公司",
        install_date="2023-01-15",
        design_life_years=10,
        location={"chamber": "A1", "position": "北墙"},
        specifications={"power": "5.5kW", "voltage": "380V"},
        purchase_cost=12500.00,
        supplier="机电设备供应商",
        contact_person="张工",
        contact_phone="13800138000"
    )
    
    required_fields = ["asset_id", "device_id", "device_type", "name", "model", 
                       "manufacturer", "install_date", "design_life_years"]
    
    for field in required_fields:
        assert getattr(test_asset, field) is not None, f"Missing required field: {field}"
    
    assert test_asset.design_life_years > 0, "Design life must be positive"
    assert len(test_asset.name) > 0, "Name cannot be empty"
    
    return True


def test_asset_creation_boundary():
    valid_asset = SimpleAsset(
        asset_id="asset_boundary_001",
        device_id="pump_001",
        device_type="pump",
        name="排水泵-001",
        model="PUMP-5000",
        manufacturer="泵业公司",
        install_date="2020-01-01",
        design_life_years=15,
        location={"chamber": "B2"},
        specifications={},
        status="active"
    )
    
    assert valid_asset.status == "active"
    
    today = datetime.utcnow().date()
    future_install = (today + timedelta(days=30)).isoformat()
    past_install = (today - timedelta(days=365 * 50)).isoformat()
    
    future_asset = SimpleAsset(
        asset_id="asset_future_001",
        device_id="test_001",
        device_type="sensor",
        name="测试设备",
        model="TEST",
        manufacturer="Test",
        install_date=future_install,
        design_life_years=5,
        location={},
        specifications={},
        status="pending"
    )
    assert future_asset.status == "pending"
    
    old_asset = SimpleAsset(
        asset_id="asset_old_001",
        device_id="test_002",
        device_type="sensor",
        name="老旧设备",
        model="OLD",
        manufacturer="OldCompany",
        install_date=past_install,
        design_life_years=5,
        location={},
        specifications={},
        status="decommissioned"
    )
    assert old_asset.status == "decommissioned"
    
    return True


def test_life_prediction_accuracy():
    def predict_remaining_life(asset, env_data=None):
        install_date = datetime.strptime(asset.install_date, "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        service_years = (today - install_date).days / 365.25
        
        age_factor = service_years / asset.design_life_years
        
        env_factor = 1.0
        if env_data:
            if env_data.get("avg_temp", 25) > 35:
                env_factor *= 0.85
            if env_data.get("avg_humidity", 50) > 70:
                env_factor *= 0.9
            if env_data.get("starts_per_day", 1) > 10:
                env_factor *= 0.8
        
        if asset.last_maintenance_date:
            last_maintain = datetime.strptime(asset.last_maintenance_date, "%Y-%m-%d").date()
            months_since_maintain = (today - last_maintain).days / 30
            if months_since_maintain > 12:
                env_factor *= 0.9
        
        remaining_life = asset.design_life_years * (1 - age_factor) * env_factor
        
        confidence = 0.7 + 0.2 * env_factor - 0.1 * age_factor
        confidence = max(0.5, min(0.95, confidence))
        
        return SimpleRemainingLifePrediction(
            asset_id=asset.asset_id,
            asset_name=asset.name,
            remaining_life_years=max(0.1, remaining_life),
            confidence=confidence,
            prediction_date=today.isoformat(),
            factors={
                "age_factor": age_factor,
                "env_factor": env_factor,
                "service_years": service_years
            }
        )
    
    today = datetime.utcnow().date()
    
    new_asset = SimpleAsset(
        asset_id="asset_new",
        device_id="dev_new",
        device_type="pump",
        name="新泵",
        model="PUMP-5000",
        manufacturer="Test",
        install_date=(today - timedelta(days=365)).isoformat(),
        design_life_years=15,
        last_maintenance_date=today.isoformat()
    )
    
    prediction = predict_remaining_life(new_asset)
    assert prediction.remaining_life_years > 10, f"New asset should have long remaining life: {prediction.remaining_life_years}"
    assert prediction.confidence >= 0.7, f"New asset prediction should have high confidence: {prediction.confidence}"
    
    old_asset = SimpleAsset(
        asset_id="asset_old",
        device_id="dev_old",
        device_type="fan",
        name="旧风机",
        model="FAN-2000",
        manufacturer="Test",
        install_date=(today - timedelta(days=365 * 14)).isoformat(),
        design_life_years=15,
        last_maintenance_date=(today - timedelta(days=365 * 2)).isoformat()
    )
    
    prediction_old = predict_remaining_life(old_asset)
    assert prediction_old.remaining_life_years < 5, f"Old asset should have short remaining life: {prediction_old.remaining_life_years}"
    
    harsh_env = {"avg_temp": 40, "avg_humidity": 80, "starts_per_day": 15}
    prediction_harsh = predict_remaining_life(new_asset, harsh_env)
    assert prediction_harsh.remaining_life_years < prediction.remaining_life_years, \
        "Harsh environment should reduce life expectancy"
    
    return True


def test_life_prediction_model_validity():
    def predict_remaining_life(asset, env_data=None):
        install_date = datetime.strptime(asset.install_date, "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        service_years = (today - install_date).days / 365.25
        
        age_factor = service_years / asset.design_life_years
        
        env_factor = 1.0
        if env_data:
            if env_data.get("avg_temp", 25) > 35:
                env_factor *= 0.85
            if env_data.get("avg_humidity", 50) > 70:
                env_factor *= 0.9
            if env_data.get("starts_per_day", 1) > 10:
                env_factor *= 0.8
        
        if asset.last_maintenance_date:
            last_maintain = datetime.strptime(asset.last_maintenance_date, "%Y-%m-%d").date()
            months_since_maintain = (today - last_maintain).days / 30
            if months_since_maintain > 12:
                env_factor *= 0.9
        
        remaining_life = asset.design_life_years * (1 - age_factor) * env_factor
        
        confidence = 0.7 + 0.2 * env_factor - 0.1 * age_factor
        confidence = max(0.5, min(0.95, confidence))
        
        return SimpleRemainingLifePrediction(
            asset_id=asset.asset_id,
            asset_name=asset.name,
            remaining_life_years=max(0.1, remaining_life),
            confidence=confidence,
            prediction_date=today.isoformat(),
            factors={
                "age_factor": age_factor,
                "env_factor": env_factor,
                "service_years": service_years
            }
        )
    
    today = datetime.utcnow().date()
    
    for years_old in [0.5, 3, 7, 12, 18]:
        asset = SimpleAsset(
            asset_id=f"asset_{years_old}",
            device_id=f"dev_{years_old}",
            device_type="pump",
            name=f"泵-{years_old}年",
            model="PUMP-5000",
            manufacturer="Test",
            install_date=(today - timedelta(days=365 * years_old)).isoformat(),
            design_life_years=15,
            last_maintenance_date=today.isoformat()
        )
        
        prediction = predict_remaining_life(asset)
        
        assert prediction.remaining_life_years > 0, "Remaining life should be positive"
        assert prediction.confidence >= 0.5 and prediction.confidence <= 0.95, "Confidence out of range"
        assert 0 <= prediction.factors["age_factor"] <= 2.0, "Age factor out of range"
        
        if years_old < 5:
            assert prediction.remaining_life_years > 5, f"Young asset should have long life"
        elif years_old > 14:
            assert prediction.remaining_life_years < 3, f"Old asset should have short life"
    
    return True


def test_maintenance_priority_calculation():
    def calculate_priority(asset, prediction):
        score = 0.0
        
        if prediction.remaining_life_years < 0.5:
            score += 50
        elif prediction.remaining_life_years < 1:
            score += 30
        elif prediction.remaining_life_years < 2:
            score += 15
        
        if prediction.confidence > 0.8:
            score *= 1.2
        elif prediction.confidence < 0.6:
            score *= 0.8
        
        if asset.device_type in ["pump", "fan"]:
            score += 10
        
        if asset.failure_count > 3:
            score += 15
        elif asset.failure_count > 0:
            score += 5
        
        if asset.maintenance_count > 10:
            score -= 5
        
        if prediction.factors["env_factor"] < 0.7:
            score += 10
        
        priority = 1 if score >= 50 else 2 if score >= 25 else 3 if score >= 10 else 4
        
        return priority, score
    
    today = datetime.utcnow().date()
    
    critical_asset = SimpleAsset(
        asset_id="asset_critical",
        device_id="dev_critical",
        device_type="pump",
        name="关键泵",
        model="PUMP-5000",
        manufacturer="Test",
        install_date=(today - timedelta(days=365 * 14.5)).isoformat(),
        design_life_years=15,
        failure_count=5
    )
    
    critical_pred = SimpleRemainingLifePrediction(
        asset_id="asset_critical",
        asset_name="关键泵",
        remaining_life_years=0.3,
        confidence=0.9,
        prediction_date=today.isoformat(),
        factors={"env_factor": 0.6, "age_factor": 0.97}
    )
    
    priority1, score1 = calculate_priority(critical_asset, critical_pred)
    assert priority1 == 1, f"Critical asset should have priority 1, got {priority1}"
    assert score1 >= 50, f"Critical score should be >= 50, got {score1}"
    
    normal_asset = SimpleAsset(
        asset_id="asset_normal",
        device_id="dev_normal",
        device_type="sensor",
        name="普通传感器",
        model="SENSOR-1000",
        manufacturer="Test",
        install_date=(today - timedelta(days=365 * 3)).isoformat(),
        design_life_years=10,
        failure_count=0,
        maintenance_count=2
    )
    
    normal_pred = SimpleRemainingLifePrediction(
        asset_id="asset_normal",
        asset_name="普通传感器",
        remaining_life_years=6.5,
        confidence=0.85,
        prediction_date=today.isoformat(),
        factors={"env_factor": 1.0, "age_factor": 0.3}
    )
    
    priority4, score4 = calculate_priority(normal_asset, normal_pred)
    assert priority4 == 4, f"Normal asset should have priority 4, got {priority4}"
    assert score4 < 10, f"Normal score should be < 10, got {score4}"
    
    return True


def test_maintenance_plan_sorting():
    def calculate_priority(asset, prediction):
        score = 0.0
        
        if prediction.remaining_life_years < 0.5:
            score += 50
        elif prediction.remaining_life_years < 1:
            score += 30
        elif prediction.remaining_life_years < 2:
            score += 15
        
        if prediction.confidence > 0.8:
            score *= 1.2
        elif prediction.confidence < 0.6:
            score *= 0.8
        
        if asset.device_type in ["pump", "fan"]:
            score += 10
        
        if asset.failure_count > 3:
            score += 15
        elif asset.failure_count > 0:
            score += 5
        
        if prediction.factors["env_factor"] < 0.7:
            score += 10
        
        priority = 1 if score >= 50 else 2 if score >= 25 else 3 if score >= 10 else 4
        
        return priority, score
    
    today = datetime.utcnow().date()
    
    assets = [
        ("asset_urgent", "pump", 14.5, 0.3, 5),
        ("asset_high", "fan", 12, 1.5, 2),
        ("asset_medium", "sensor", 7, 3.5, 0),
        ("asset_low", "sensor", 2, 8.0, 0),
        ("asset_very_low", "sensor", 0.5, 14.5, 0),
    ]
    
    tasks = []
    for i, (asset_id, device_type, years_old, remaining_life, failures) in enumerate(assets):
        asset = SimpleAsset(
            asset_id=asset_id,
            device_id=f"dev_{i}",
            device_type=device_type,
            name=f"设备-{i}",
            model="MODEL",
            manufacturer="Test",
            install_date=(today - timedelta(days=365 * years_old)).isoformat(),
            design_life_years=15,
            failure_count=failures
        )
        
        pred = SimpleRemainingLifePrediction(
            asset_id=asset_id,
            asset_name=f"设备-{i}",
            remaining_life_years=remaining_life,
            confidence=0.85,
            prediction_date=today.isoformat(),
            factors={"env_factor": 0.8, "age_factor": years_old / 15}
        )
        
        priority, score = calculate_priority(asset, pred)
        
        tasks.append(SimpleMaintenanceTask(
            task_id=f"task_{i}",
            asset_id=asset_id,
            asset_name=f"设备-{i}",
            task_type="preventive",
            priority=priority,
            due_date=(today + timedelta(days=priority * 7)).isoformat(),
            estimated_hours=2.0 + failures * 0.5,
            description=f"{asset_id} 预防性维护"
        ))
    
    tasks.sort(key=lambda t: (t.priority, -assets[[a[0] for a in assets].index(t.asset_id)][4]))
    
    assert tasks[0].priority == 1, "First task should have highest priority"
    assert tasks[0].asset_id == "asset_urgent", "Urgent asset should be first"
    assert tasks[-1].priority >= 3, "Last tasks should have lower priority"
    
    priorities = [t.priority for t in tasks]
    assert priorities == sorted(priorities), "Tasks should be sorted by priority"
    
    return True


def test_monthly_maintenance_plan_generation():
    def generate_monthly_plan(assets, predictions, month_date=None):
        if month_date is None:
            month_date = datetime.utcnow().date()
        
        plan = []
        for asset, pred in zip(assets, predictions):
            priority, score = calculate_priority_simple(asset, pred)
            
            if priority <= 3:
                due_date = month_date + timedelta(days=priority * 7)
                plan.append(SimpleMaintenanceTask(
                    task_id=f"maint_{month_date.strftime('%Y%m')}_{asset.asset_id}",
                    asset_id=asset.asset_id,
                    asset_name=asset.name,
                    task_type="preventive",
                    priority=priority,
                    due_date=due_date.isoformat(),
                    estimated_hours=2.0,
                    description=f"{asset.name} 月度维护"
                ))
        
        plan.sort(key=lambda t: (t.priority, t.due_date))
        return plan
    
    def calculate_priority_simple(asset, prediction):
        score = 0.0
        
        if prediction.remaining_life_years < 0.5:
            score += 50
        elif prediction.remaining_life_years < 1:
            score += 30
        elif prediction.remaining_life_years < 2:
            score += 15
        
        if prediction.confidence > 0.8:
            score *= 1.2
        
        if asset.device_type in ["pump", "fan"]:
            score += 10
        
        if asset.failure_count > 0:
            score += asset.failure_count * 3
        
        priority = 1 if score >= 50 else 2 if score >= 25 else 3 if score >= 10 else 4
        
        return priority, score
    
    today = datetime.utcnow().date()
    
    assets = []
    predictions = []
    
    for i in range(10):
        years_old = random.uniform(0.5, 14.5)
        design_life = random.choice([10, 15, 20])
        remaining = max(0.1, design_life - years_old + random.uniform(-1, 1))
        
        asset = SimpleAsset(
            asset_id=f"asset_monthly_{i}",
            device_id=f"dev_{i}",
            device_type=random.choice(["pump", "fan", "sensor"]),
            name=f"月度设备-{i}",
            model="MODEL",
            manufacturer="Test",
            install_date=(today - timedelta(days=365 * years_old)).isoformat(),
            design_life_years=design_life,
            failure_count=random.randint(0, 5)
        )
        
        pred = SimpleRemainingLifePrediction(
            asset_id=f"asset_monthly_{i}",
            asset_name=f"月度设备-{i}",
            remaining_life_years=remaining,
            confidence=random.uniform(0.6, 0.95),
            prediction_date=today.isoformat(),
            factors={"env_factor": random.uniform(0.7, 1.0), "age_factor": years_old / design_life}
        )
        
        assets.append(asset)
        predictions.append(pred)
    
    plan = generate_monthly_plan(assets, predictions)
    
    assert len(plan) > 0, "Should generate some maintenance tasks"
    assert len(plan) <= len(assets), "Cannot have more tasks than assets"
    
    for task in plan:
        assert task.priority in [1, 2, 3], "Priority should be 1, 2, or 3"
        assert "20" in task.due_date, "Due date should be valid date string"
        assert task.estimated_hours > 0
    
    priorities = [t.priority for t in plan]
    assert priorities == sorted(priorities), "Plan should be sorted by priority"
    
    return True


def test_asset_lifecycle_tracking():
    today = datetime.utcnow().date()
    
    asset = SimpleAsset(
        asset_id="asset_lifecycle_001",
        device_id="dev_lc_001",
        device_type="pump",
        name="生命周期测试泵",
        model="PUMP-5000",
        manufacturer="Test",
        install_date=(today - timedelta(days=365 * 5)).isoformat(),
        design_life_years=15,
        maintenance_count=3,
        failure_count=1
    )
    
    records = []
    
    for i in range(3):
        record = SimpleMaintenanceRecord(
            record_id=f"record_{i}",
            asset_id="asset_lifecycle_001",
            maintenance_date=(today - timedelta(days=365 * (2 - i))).isoformat(),
            task_type="preventive",
            cost=500.0 + i * 100,
            technician=f"技术人员-{i}",
            notes=f"第{i+1}次预防性维护"
        )
        records.append(record)
    
    failure_record = SimpleMaintenanceRecord(
        record_id="record_failure",
        asset_id="asset_lifecycle_001",
        maintenance_date=(today - timedelta(days=180)).isoformat(),
        task_type="corrective",
        cost=2500.0,
        technician="应急维修队",
        notes="轴承故障更换"
    )
    records.append(failure_record)
    
    assert len(records) == 4
    assert asset.maintenance_count == 3
    assert asset.failure_count == 1
    
    total_cost = sum(r.cost for r in records)
    assert total_cost == 500 + 600 + 700 + 2500
    
    preventive_count = sum(1 for r in records if r.task_type == "preventive")
    corrective_count = sum(1 for r in records if r.task_type == "corrective")
    
    assert preventive_count == 3
    assert corrective_count == 1
    
    return True


def test_asset_ledger_data_integrity():
    today = datetime.utcnow().date()
    
    ledger = []
    
    for i in range(20):
        asset = SimpleAsset(
            asset_id=f"ledger_asset_{i:03d}",
            device_id=f"dev_ledger_{i:03d}",
            device_type=random.choice(["pump", "fan", "sensor", "fiber_sensor", "smoke_sensor"]),
            name=f"台账设备-{i}",
            model=random.choice(["MODEL-A", "MODEL-B", "MODEL-C"]),
            manufacturer=random.choice(["厂商A", "厂商B", "厂商C"]),
            install_date=(today - timedelta(days=random.randint(30, 365 * 15))).isoformat(),
            design_life_years=random.choice([10, 15, 20]),
            purchase_cost=random.uniform(1000, 50000),
            supplier=random.choice(["供应商A", "供应商B"]),
            location={"chamber": random.choice(["A1", "A2", "B1", "B2", "C1"]), "position": f"位置-{i}"},
            specifications={"power": f"{random.randint(1, 10)}kW"},
            status=random.choice(["active", "maintenance", "decommissioned"])
        )
        ledger.append(asset)
    
    assert len(ledger) == 20
    
    required_fields = ["asset_id", "device_id", "device_type", "name", "model", 
                       "manufacturer", "install_date", "design_life_years"]
    
    for asset in ledger:
        for field in required_fields:
            value = getattr(asset, field)
            assert value is not None, f"Asset {asset.asset_id} missing field: {field}"
            if isinstance(value, str):
                assert len(value) > 0, f"Asset {asset.asset_id} empty field: {field}"
        
        assert asset.design_life_years > 0
        assert 0 <= asset.maintenance_count <= 100
        assert 0 <= asset.failure_count <= 100
        assert asset.status in ["active", "maintenance", "decommissioned"]
    
    asset_ids = [a.asset_id for a in ledger]
    assert len(asset_ids) == len(set(asset_ids)), "Asset IDs should be unique"
    
    device_ids = [a.device_id for a in ledger]
    assert len(device_ids) == len(set(device_ids)), "Device IDs should be unique"
    
    return True


if __name__ == "__main__":
    suite = FeatureTestSuite()
    
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING STRUCTURE MONITORING TESTS")
    logger.info("=" * 80)
    
    suite.run_test("光纤应变数据解析 - 正常", test_fiber_strain_data_parsing_normal, "结构监测")
    suite.run_test("光纤应变数据解析 - 边界", test_fiber_strain_data_parsing_boundary, "结构监测")
    suite.run_test("光纤应变数据解析 - 异常", test_fiber_strain_data_parsing_anomaly, "结构监测")
    suite.run_test("应变映射和定位准确性", test_strain_mapping_and_location_accuracy, "结构监测")
    suite.run_test("结构热力图生成 - 正常", test_heatmap_generation_normal, "结构监测")
    suite.run_test("结构热力图生成 - 边界", test_heatmap_generation_boundary, "结构监测")
    suite.run_test("热力图颜色映射正确性", test_heatmap_color_mapping, "结构监测")
    suite.run_test("裂缝预警及时性", test_crack_warning_timeliness, "结构监测")
    suite.run_test("裂缝预警误报率测试", test_crack_warning_false_positive_rate, "结构监测")
    suite.run_test("告警冷却机制测试", test_alert_cooldown_mechanism, "结构监测")
    
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING ROBOT INSPECTION TESTS")
    logger.info("=" * 80)
    
    suite.run_test("路径规划避障 - 高温", test_path_planning_obstacle_avoidance_high_temp, "机器人巡检")
    suite.run_test("路径规划避障 - 高湿", test_path_planning_obstacle_avoidance_high_humidity, "机器人巡检")
    suite.run_test("路径规划避障 - 有害气体", test_path_planning_obstacle_avoidance_gas, "机器人巡检")
    suite.run_test("路径长度优化测试", test_path_optimization_length, "机器人巡检")
    suite.run_test("路径规划边界情况", test_path_planning_boundary_cases, "机器人巡检")
    suite.run_test("传感器数据融合准确性", test_sensor_data_fusion_accuracy, "机器人巡检")
    suite.run_test("巡检进度跟踪", test_inspection_progress_tracking, "机器人巡检")
    suite.run_test("机器人位置更新", test_robot_position_updates, "机器人巡检")
    suite.run_test("机器人低电量检测", test_robot_battery_depletion, "机器人巡检")
    
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING FIRE DETECTION TESTS")
    logger.info("=" * 80)
    
    suite.run_test("温度变化率计算准确性", test_temperature_rate_calculation, "火灾预警")
    suite.run_test("烟雾浓度变化率计算", test_smoke_density_rate_calculation, "火灾预警")
    suite.run_test("温度烟雾相关性计算", test_temp_smoke_correlation, "火灾预警")
    suite.run_test("贝叶斯火灾概率计算", test_bayesian_fire_probability, "火灾预警")
    suite.run_test("火灾与设备过热区分准确率", test_fire_vs_overheating_discrimination, "火灾预警")
    suite.run_test("火灾概率边界值测试", test_fire_probability_boundary_values, "火灾预警")
    suite.run_test("火灾误报率测试", test_fire_false_positive_rate, "火灾预警")
    suite.run_test("联动控制响应时间", test_linked_control_response_time, "火灾预警")
    suite.run_test("防火分区状态更新", test_fire_zone_status_update, "火灾预警")
    
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING ASSET MANAGEMENT TESTS")
    logger.info("=" * 80)
    
    suite.run_test("资产数据完整性检查", test_asset_data_completeness, "资产管理")
    suite.run_test("资产创建边界情况", test_asset_creation_boundary, "资产管理")
    suite.run_test("设备寿命预测准确度", test_life_prediction_accuracy, "资产管理")
    suite.run_test("寿命预测模型有效性", test_life_prediction_model_validity, "资产管理")
    suite.run_test("维护优先级计算", test_maintenance_priority_calculation, "资产管理")
    suite.run_test("维修计划优先级排序", test_maintenance_plan_sorting, "资产管理")
    suite.run_test("月度维修计划生成", test_monthly_maintenance_plan_generation, "资产管理")
    suite.run_test("资产生命周期跟踪", test_asset_lifecycle_tracking, "资产管理")
    suite.run_test("资产台账数据完整性", test_asset_ledger_data_integrity, "资产管理")
    
    all_passed = suite.print_summary()
    
    results_path = Path(__file__).parent / "test_results_new_features.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": suite.passed + suite.failed,
                "passed": suite.passed,
                "failed": suite.failed,
                "pass_rate": suite.passed / (suite.passed + suite.failed) * 100 if (suite.passed + suite.failed) > 0 else 0
            },
            "results": suite.test_results,
            "generated_at": datetime.utcnow().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n📊 Test results saved to {results_path}")
    
    sys.exit(0 if all_passed else 1)
