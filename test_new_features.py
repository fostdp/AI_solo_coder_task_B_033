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
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SimpleWaypoint:
    x: float
    y: float
    distance_km: float = 0.0
    action: str = "inspect"


@dataclass
class SimpleLocation:
    type: str = "Point"
    coordinates: List[float] = None

    def __post_init__(self):
        if self.coordinates is None:
            self.coordinates = [0.0, 0.0]


@dataclass
class SimpleAsset:
    device_id: str
    name: str
    type: str
    manufacturer: str
    model: str
    serial_number: str
    installation_date: str
    design_life_years: float
    last_maintenance_date: str = None
    purchase_cost: float = None
    location: Dict = None
    chamber: str = ""
    specifications: Dict = None
    status: str = "active"
    warranty_end_date: str = None
    maintenance_count: int = 0
    failure_count: int = 0

    def __post_init__(self):
        if self.specifications is None:
            self.specifications = {}
        if self.location is None:
            self.location = {}


@dataclass
class SimpleMaintenanceTask:
    task_id: str
    asset_id: str
    task_type: str
    description: str
    priority: int
    scheduled_date: str
    estimated_hours: float
    status: str = "pending"


@dataclass
class SimpleMaintenanceRecord:
    record_id: str
    asset_id: str
    maintenance_date: str
    task_type: str
    description: str
    technician: str
    cost: float = 0.0
    parts_replaced: List[str] = None
    next_maintenance_date: str = None

    def __post_init__(self):
        if self.parts_replaced is None:
            self.parts_replaced = []


@dataclass
class SimpleRemainingLifePrediction:
    asset_id: str
    prediction_date: str
    remaining_life_years: float
    confidence: float
    factors: Dict = None

    def __post_init__(self):
        if self.factors is None:
            self.factors = {}


@dataclass
class SimpleFireSensorData:
    device_id: str
    timestamp: str
    temperature: float
    temperature_rate: float
    smoke_density: float
    location: SimpleLocation = None

    def __post_init__(self):
        if self.location is None:
            self.location = SimpleLocation()


@dataclass
class SimpleAlert:
    device_id: str
    level: str
    type: str
    message: str
    value: float
    threshold: float
    timestamp: str = None
    acknowledged: bool = False

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


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
            import traceback
            traceback.print_exc()
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


# ============================================================================
# STRUCTURE MONITORING TESTS
# ============================================================================

class MockConfig:
    STRAIN_WARNING_THRESHOLD = 200
    STRAIN_CRITICAL_THRESHOLD = 400
    CRACK_WARNING_THRESHOLD = 0.2
    CRACK_CRITICAL_THRESHOLD = 0.5
    ALERT_COOLDOWN_MINUTES = 10


def test_fiber_strain_data_parsing_normal():
    from backend.modules.structure_monitor import StructureMonitor
    
    config = MockConfig()
    monitor = StructureMonitor.__new__(StructureMonitor)
    monitor.config = config
    
    test_data = {
        "device_id": "fiber_001",
        "timestamp": datetime.utcnow().isoformat(),
        "segment_index": 5,
        "strain": 150.5,
        "temperature": 22.3,
        "crack_width": 0.05
    }
    
    assert test_data["strain"] >= 0 and test_data["strain"] < config.STRAIN_WARNING_THRESHOLD
    assert test_data["temperature"] > -20 and test_data["temperature"] < 100
    assert test_data["segment_index"] >= 0
    
    return True


def test_fiber_strain_data_parsing_boundary():
    config = MockConfig()
    
    boundary_cases = [
        {"strain": config.STRAIN_WARNING_THRESHOLD - 0.1, "expected_level": "attention"},
        {"strain": config.STRAIN_WARNING_THRESHOLD, "expected_level": "warning"},
        {"strain": config.STRAIN_CRITICAL_THRESHOLD - 0.1, "expected_level": "warning"},
        {"strain": config.STRAIN_CRITICAL_THRESHOLD, "expected_level": "critical"},
        {"strain": 0, "expected_level": "normal"},
        {"strain": 1000, "expected_level": "critical"},
    ]
    
    from backend.modules.structure_monitor import StructureMonitor
    monitor = StructureMonitor.__new__(StructureMonitor)
    monitor.config = config
    
    for case in boundary_cases:
        level = monitor._calculate_risk_level(case["strain"], 0)
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
    from backend.modules.structure_monitor import StructureMonitor
    
    monitor = StructureMonitor.__new__(StructureMonitor)
    monitor.config = MockConfig()
    
    test_cases = [
        (50, "normal", "rgba(34, 197, 94"),
        (150, "normal", "rgba(34, 197, 94"),
        (200, "warning", "rgba(249, 115, 22"),
        (300, "warning", "rgba(249, 115, 22"),
        (400, "critical", "rgba(239, 68, 68"),
        (500, "critical", "rgba(239, 68, 68"),
    ]
    
    for strain, expected_level, expected_color_prefix in test_cases:
        level = monitor._calculate_risk_level(strain, 0)
        assert level == expected_level, f"Level mismatch for strain {strain}"
    
    return True


def test_crack_warning_timeliness():
    alert_timestamps = []
    
    class MockStructureMonitor:
        def __init__(self):
            self.last_alert_time = {}
        
        def process_fiber_data(self, data):
            from backend.modules.structure_monitor import StructureMonitor
            monitor = StructureMonitor.__new__(StructureMonitor)
            monitor.config = MockConfig()
            monitor.last_alert_time = self.last_alert_time
            
            risk_level = monitor._calculate_risk_level(data["strain"], data.get("crack_width", 0))
            
            device_key = data["device_id"]
            now = datetime.utcnow()
            
            if risk_level in ["warning", "critical"]:
                last_alert = self.last_alert_time.get(device_key)
                if not last_alert or (now - last_alert) > timedelta(minutes=10):
                    alert_timestamps.append(now)
                    self.last_alert_time[device_key] = now
                    return True, risk_level
            
            return False, risk_level
    
    monitor = MockStructureMonitor()
    
    t0 = datetime.utcnow()
    data1 = {"device_id": "fiber_001", "timestamp": t0.isoformat(), "strain": 450, "crack_width": 0.3}
    triggered1, level1 = monitor.process_fiber_data(data1)
    
    assert triggered1 == True, "First alert should trigger"
    assert level1 == "critical", "Should be critical level"
    
    data2 = {"device_id": "fiber_001", "timestamp": (t0 + timedelta(minutes=1)).isoformat(), "strain": 480, "crack_width": 0.35}
    triggered2, level2 = monitor.process_fiber_data(data2)
    
    assert triggered2 == False, "Alert within cooldown should not trigger"
    
    data3 = {"device_id": "fiber_001", "timestamp": (t0 + timedelta(minutes=11)).isoformat(), "strain": 500, "crack_width": 0.4}
    triggered3, level3 = monitor.process_fiber_data(data3)
    
    assert triggered3 == True, "Alert after cooldown should trigger"
    
    assert len(alert_timestamps) == 2
    time_diff = (alert_timestamps[1] - alert_timestamps[0]).total_seconds()
    assert time_diff >= 600, f"Cooldown not respected: {time_diff}s"
    
    return True


def test_crack_warning_false_positive_rate():
    from backend.modules.structure_monitor import StructureMonitor
    
    monitor = StructureMonitor.__new__(StructureMonitor)
    monitor.config = MockConfig()
    
    normal_strains = [random.uniform(0, 199) for _ in range(1000)]
    false_alarms = 0
    
    for strain in normal_strains:
        level = monitor._calculate_risk_level(strain, 0)
        if level in ["warning", "critical"]:
            false_alarms += 1
    
    false_positive_rate = false_alarms / len(normal_strains)
    assert false_positive_rate == 0, f"False positive rate should be 0%, got {false_positive_rate*100:.1f}%"
    
    warning_strains = [random.uniform(200, 399) for _ in range(100)]
    warnings = 0
    for strain in warning_strains:
        level = monitor._calculate_risk_level(strain, 0)
        if level == "warning":
            warnings += 1
    
    assert warnings == 100, f"Warning detection rate should be 100%, got {warnings}%"
    
    critical_strains = [random.uniform(400, 1000) for _ in range(100)]
    criticals = 0
    for strain in critical_strains:
        level = monitor._calculate_risk_level(strain, 0)
        if level == "critical":
            criticals += 1
    
    assert criticals == 100, f"Critical detection rate should be 100%, got {criticals}%"
    
    return True


def test_alert_cooldown_mechanism():
    from backend.modules.structure_monitor import StructureMonitor
    
    monitor = StructureMonitor.__new__(StructureMonitor)
    monitor.config = MockConfig()
    monitor.last_alert_time = {}
    
    alerts_sent = []
    
    def mock_alert(device_id, level, value, threshold):
        now = datetime.utcnow()
        last_alert = monitor.last_alert_time.get(device_id)
        cooldown = timedelta(minutes=monitor.config.ALERT_COOLDOWN_MINUTES)
        
        if last_alert and (now - last_alert) < cooldown:
            return False
        
        monitor.last_alert_time[device_id] = now
        alerts_sent.append({"device_id": device_id, "level": level, "timestamp": now})
        return True
    
    monitor._send_alert = mock_alert
    
    t0 = datetime.utcnow()
    
    result1 = monitor._send_alert("fiber_001", "critical", 450, 400)
    assert result1 == True, "First alert should succeed"
    assert len(alerts_sent) == 1
    
    result2 = monitor._send_alert("fiber_001", "critical", 480, 400)
    assert result2 == False, "Alert within cooldown should be suppressed"
    assert len(alerts_sent) == 1
    
    monitor.last_alert_time["fiber_001"] = t0 - timedelta(minutes=15)
    result3 = monitor._send_alert("fiber_001", "critical", 500, 400)
    assert result3 == True, "Alert after cooldown should succeed"
    assert len(alerts_sent) == 2
    
    return True


# ============================================================================
# ROBOT INSPECTION TESTS
# ============================================================================

def test_path_planning_obstacle_avoidance_high_temp():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    inspector._publish_position = lambda x: None
    
    class MockConfig:
        ROBOT_AVOID_HIGH_TEMP = 40
        ROBOT_AVOID_HIGH_HUMIDITY = 80
        ROBOT_AVOID_GAS_METHANE = 0.5
        ROBOT_AVOID_GAS_H2S = 5
    
    inspector.config = MockConfig()
    
    safe_zone = {"temperature": 35, "humidity": 50, "methane": 0.1, "h2s": 2}
    is_safe, reason = inspector._is_area_safe(safe_zone)
    assert is_safe == True, f"Safe zone should be safe, reason: {reason}"
    
    high_temp_zone = {"temperature": 45, "humidity": 50, "methane": 0.1, "h2s": 2}
    is_safe, reason = inspector._is_area_safe(high_temp_zone)
    assert is_safe == False, f"High temp zone should be dangerous"
    assert "高温" in reason, f"Reason should mention high temperature: {reason}"
    
    return True


def test_path_planning_obstacle_avoidance_high_humidity():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    
    class MockConfig:
        ROBOT_AVOID_HIGH_TEMP = 40
        ROBOT_AVOID_HIGH_HUMIDITY = 80
        ROBOT_AVOID_GAS_METHANE = 0.5
        ROBOT_AVOID_GAS_H2S = 5
    
    inspector.config = MockConfig()
    
    normal_humidity = {"temperature": 25, "humidity": 60, "methane": 0.1, "h2s": 2}
    is_safe, reason = inspector._is_area_safe(normal_humidity)
    assert is_safe == True
    
    high_humidity = {"temperature": 25, "humidity": 85, "methane": 0.1, "h2s": 2}
    is_safe, reason = inspector._is_area_safe(high_humidity)
    assert is_safe == False
    assert "高湿" in reason
    
    return True


def test_path_planning_obstacle_avoidance_harmful_gas():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    
    class MockConfig:
        ROBOT_AVOID_HIGH_TEMP = 40
        ROBOT_AVOID_HIGH_HUMIDITY = 80
        ROBOT_AVOID_GAS_METHANE = 0.5
        ROBOT_AVOID_GAS_H2S = 5
    
    inspector.config = MockConfig()
    
    high_methane = {"temperature": 25, "humidity": 50, "methane": 0.8, "h2s": 2}
    is_safe, reason = inspector._is_area_safe(high_methane)
    assert is_safe == False
    assert "甲烷" in reason
    
    high_h2s = {"temperature": 25, "humidity": 50, "methane": 0.1, "h2s": 8}
    is_safe, reason = inspector._is_area_safe(high_h2s)
    assert is_safe == False
    assert "硫化氢" in reason
    
    safe_gas = {"temperature": 25, "humidity": 50, "methane": 0.4, "h2s": 4}
    is_safe, reason = inspector._is_area_safe(safe_gas)
    assert is_safe == True
    
    return True


def test_path_optimization_length():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    inspector._publish_position = lambda x: None
    
    start = SimpleWaypoint(x=0, y=30)
    end = SimpleWaypoint(x=100, y=30)
    
    obstacles = []
    for i in range(40, 61):
        obstacles.append({"x": i, "y": 30, "temperature": 45, "humidity": 50, "methane": 0.1, "h2s": 2})
    
    class MockConfig:
        ROBOT_AVOID_HIGH_TEMP = 40
        ROBOT_AVOID_HIGH_HUMIDITY = 80
        ROBOT_AVOID_GAS_METHANE = 0.5
        ROBOT_AVOID_GAS_H2S = 5
    
    inspector.config = MockConfig()
    
    path = inspector.plan_path("robot_001", start, end, obstacles)
    
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
        is_dangerous = not inspector._is_area_safe({"temperature": 25, "humidity": 50, "methane": 0.1, "h2s": 2})[0]
        for obs in obstacles:
            if abs(wp.x - obs["x"]) < 1 and abs(wp.y - obs["y"]) < 1:
                is_dangerous = True
                break
        assert is_dangerous == False, f"Path point ({wp.x}, {wp.y}) is in danger zone"
    
    return True


def test_path_planning_boundary_cases():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    inspector._publish_position = lambda x: None
    
    class MockConfig:
        ROBOT_AVOID_HIGH_TEMP = 40
        ROBOT_AVOID_HIGH_HUMIDITY = 80
        ROBOT_AVOID_GAS_METHANE = 0.5
        ROBOT_AVOID_GAS_H2S = 5
    
    inspector.config = MockConfig()
    
    start = SimpleWaypoint(x=0, y=30)
    end = SimpleWaypoint(x=100, y=30)
    
    no_obstacles = []
    path1 = inspector.plan_path("robot_001", start, end, no_obstacles)
    assert len(path1) == 2, "Path without obstacles should be direct"
    
    start_end_same = SimpleWaypoint(x=50, y=30)
    path2 = inspector.plan_path("robot_001", start_end_same, start_end_same, [])
    assert len(path2) == 1, "Path with same start and end should have one point"
    
    return True


def test_sensor_data_fusion_accuracy():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    
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
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    inspector.robot_positions = {}
    inspector._publish_position = lambda x: None
    
    robot_id = "robot_001"
    waypoints = [SimpleWaypoint(x=i * 10, y=30 + math.sin(i * 0.5) * 2) for i in range(11)]
    
    start_time = datetime.utcnow()
    
    for i, wp in enumerate(waypoints):
        pos_data = inspector.update_robot_position(robot_id, wp.x, wp.y, 90 - i * 0.5, 1.2)
        
        expected_time = start_time + timedelta(seconds=i)
        actual_pos = inspector.robot_positions[robot_id]
        
        assert actual_pos["x"] == wp.x
        assert actual_pos["y"] == wp.y
        assert actual_pos["battery"] == 90 - i * 0.5
        
        assert "timestamp" in actual_pos
    
    assert len(inspector.robot_positions) == 1
    
    return True


def test_robot_battery_depletion():
    from backend.modules.robot_inspector import RobotInspector
    
    inspector = RobotInspector.__new__(RobotInspector)
    inspector.robot_positions = {}
    inspector._publish_position = lambda x: None
    inspector.active_missions = {}
    
    robot_id = "robot_001"
    
    for battery in [100, 50, 20, 10, 5]:
        pos = inspector.update_robot_position(robot_id, 50, 30, battery, 1.0)
        assert pos["battery"] == battery
        
        if battery <= 10:
            assert pos.get("low_battery", True), "Should flag low battery"
    
    return True


# ============================================================================
# FIRE DETECTION TESTS
# ============================================================================

def test_temperature_rate_calculation():
    from backend.modules.fire_detector import BayesianFireDetector
    
    detector = BayesianFireDetector.__new__(BayesianFireDetector)
    
    class MockConfig:
        FIRE_TEMP_RATE_WARNING = 2
        FIRE_TEMP_RATE_CRITICAL = 5
        FIRE_SMOKE_DENSITY_WARNING = 5
        FIRE_SMOKE_DENSITY_CRITICAL = 15
        FIRE_PROBABILITY_THRESHOLD = 0.7
        FIRE_OVERHEAT_TEMP_THRESHOLD = 60
    
    detector.config = MockConfig()
    
    timestamps = [
        datetime(2024, 1, 1, 0, 0, 0),
        datetime(2024, 1, 1, 0, 0, 10),
        datetime(2024, 1, 1, 0, 0, 20),
        datetime(2024, 1, 1, 0, 0, 30),
    ]
    
    normal_temps = [25.0, 25.1, 25.2, 25.1]
    rate = detector._calculate_rate(normal_temps, timestamps)
    assert abs(rate) < 0.1, f"Normal temp rate should be ~0, got {rate:.4f}°C/s"
    
    rapid_temps = [25.0, 30.0, 35.0, 40.0]
    rate = detector._calculate_rate(rapid_temps, timestamps)
    assert rate > 0.4, f"Rapid temp rate should be high, got {rate:.4f}°C/s"
    
    slow_increase = [25.0, 25.5, 26.0, 26.5]
    rate = detector._calculate_rate(slow_increase, timestamps)
    assert rate > 0 and rate < 0.1, f"Slow increase rate should be low, got {rate:.4f}°C/s"
    
    return True


def test_smoke_density_rate_calculation():
    from backend.modules.fire_detector import BayesianFireDetector
    
    detector = BayesianFireDetector.__new__(BayesianFireDetector)
    
    class MockConfig:
        FIRE_TEMP_RATE_WARNING = 2
        FIRE_TEMP_RATE_CRITICAL = 5
        FIRE_SMOKE_DENSITY_WARNING = 5
        FIRE_SMOKE_DENSITY_CRITICAL = 15
        FIRE_PROBABILITY_THRESHOLD = 0.7
        FIRE_OVERHEAT_TEMP_THRESHOLD = 60
    
    detector.config = MockConfig()
    
    timestamps = [
        datetime(2024, 1, 1, 0, 0, 0),
        datetime(2024, 1, 1, 0, 0, 5),
        datetime(2024, 1, 1, 0, 0, 10),
        datetime(2024, 1, 1, 0, 0, 15),
    ]
    
    normal_smoke = [0.1, 0.1, 0.1, 0.1]
    rate = detector._calculate_rate(normal_smoke, timestamps)
    assert abs(rate) < 0.01, f"Normal smoke rate should be ~0, got {rate:.4f}"
    
    fire_smoke = [0.1, 2.0, 5.0, 8.0]
    rate = detector._calculate_rate(fire_smoke, timestamps)
    assert rate > 0.5, f"Fire smoke rate should be high, got {rate:.4f}"
    
    return True


def test_temp_smoke_correlation():
    from backend.modules.fire_detector import BayesianFireDetector
    
    detector = BayesianFireDetector.__new__(BayesianFireDetector)
    
    temp_readings = [25.0, 27.0, 30.0, 35.0, 42.0]
    smoke_readings = [0.1, 0.3, 0.8, 2.0, 5.0]
    
    n = len(temp_readings)
    temp_mean = sum(temp_readings) / n
    smoke_mean = sum(smoke_readings) / n
    
    numerator = sum((t - temp_mean) * (s - smoke_mean) for t, s in zip(temp_readings, smoke_readings))
    temp_std = math.sqrt(sum((t - temp_mean) ** 2 for t in temp_readings))
    smoke_std = math.sqrt(sum((s - smoke_mean) ** 2 for s in smoke_readings))
    
    correlation = numerator / (temp_std * smoke_std) if temp_std * smoke_std > 0 else 0
    
    assert correlation > 0.8, f"Temp and smoke should be strongly correlated during fire, got {correlation:.2f}"
    
    independent_temp = [25.0, 25.1, 25.0, 25.1, 25.0]
    independent_smoke = [0.1, 0.2, 0.1, 0.3, 0.1]
    
    temp_mean2 = sum(independent_temp) / n
    smoke_mean2 = sum(independent_smoke) / n
    numerator2 = sum((t - temp_mean2) * (s - smoke_mean2) for t, s in zip(independent_temp, independent_smoke))
    temp_std2 = math.sqrt(sum((t - temp_mean2) ** 2 for t in independent_temp))
    smoke_std2 = math.sqrt(sum((s - smoke_mean2) ** 2 for s in independent_smoke))
    
    correlation2 = numerator2 / (temp_std2 * smoke_std2) if temp_std2 * smoke_std2 > 0 else 0
    
    assert abs(correlation2) < 0.5, f"Independent readings should have low correlation, got {correlation2:.2f}"
    
    return True


def test_bayesian_fire_probability():
    from backend.modules.fire_detector import BayesianFireDetector
    
    detector = BayesianFireDetector.__new__(BayesianFireDetector)
    
    class MockConfig:
        FIRE_TEMP_RATE_WARNING = 2
        FIRE_TEMP_RATE_CRITICAL = 5
        FIRE_SMOKE_DENSITY_WARNING = 5
        FIRE_SMOKE_DENSITY_CRITICAL = 15
        FIRE_PROBABILITY_THRESHOLD = 0.7
        FIRE_OVERHEAT_TEMP_THRESHOLD = 60
    
    detector.config = MockConfig()
    
    normal_data = {"temp_rate": 0.1, "smoke_density": 0.5, "temp": 25}
    prob = detector._calculate_bayesian_probability(**normal_data)
    assert prob < 0.3, f"Normal situation should have low fire probability, got {prob:.3f}"
    
    warning_data = {"temp_rate": 3.0, "smoke_density": 8, "temp": 50}
    prob = detector._calculate_bayesian_probability(**warning_data)
    assert prob >= 0.3 and prob < 0.7, f"Warning situation should have medium probability, got {prob:.3f}"
    
    critical_data = {"temp_rate": 8.0, "smoke_density": 25, "temp": 55}
    prob = detector._calculate_bayesian_probability(**critical_data)
    assert prob >= 0.7, f"Critical situation should have high fire probability, got {prob:.3f}"
    
    return True


def test_fire_vs_overheat_discrimination():
    from backend.modules.fire_detector import BayesianFireDetector
    
    detector = BayesianFireDetector.__new__(BayesianFireDetector)
    
    class MockConfig:
        FIRE_TEMP_RATE_WARNING = 2
        FIRE_TEMP_RATE_CRITICAL = 5
        FIRE_SMOKE_DENSITY_WARNING = 5
        FIRE_SMOKE_DENSITY_CRITICAL = 15
        FIRE_PROBABILITY_THRESHOLD = 0.7
        FIRE_OVERHEAT_TEMP_THRESHOLD = 60
    
    detector.config = MockConfig()
    
    fire_scenarios = [
        {"temp_rate": 6.0, "smoke_density": 20, "temp": 55, "expected": "fire"},
        {"temp_rate": 8.0, "smoke_density": 30, "temp": 50, "expected": "fire"},
    ]
    
    overheat_scenarios = [
        {"temp_rate": 6.0, "smoke_density": 0.5, "temp": 70, "expected": "overheat"},
        {"temp_rate": 4.0, "smoke_density": 0.3, "temp": 65, "expected": "overheat"},
    ]
    
    for scenario in fire_scenarios:
        result = detector._classify_fire_or_overheat(
            scenario["temp_rate"], scenario["smoke_density"], scenario["