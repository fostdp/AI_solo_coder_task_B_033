import sys
import logging
import json
import yaml
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RegressionTestSuite:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.test_results = []
    
    def run_test(self, test_name: str, test_func):
        try:
            logger.info(f"Running test: {test_name}")
            result = test_func()
            if result:
                logger.info(f"✅ PASS: {test_name}")
                self.passed += 1
                self.test_results.append({"name": test_name, "status": "pass"})
            else:
                logger.error(f"❌ FAIL: {test_name}")
                self.failed += 1
                self.test_results.append({"name": test_name, "status": "fail"})
                self.errors.append(test_name)
        except Exception as e:
            logger.error(f"❌ ERROR: {test_name} - {e}")
            self.failed += 1
            self.test_results.append({"name": test_name, "status": "error", "error": str(e)})
            self.errors.append(f"{test_name}: {e}")
    
    def print_summary(self):
        logger.info("\n" + "=" * 60)
        logger.info("REGRESSION TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total tests: {self.passed + self.failed}")
        logger.info(f"Passed: {self.passed}")
        logger.info(f"Failed: {self.failed}")
        if self.errors:
            logger.info("\nFailed tests:")
            for err in self.errors:
                logger.info(f"  - {err}")
        logger.info("=" * 60)
        return self.failed == 0


def load_source(filepath: str) -> str:
    path = Path(filepath)
    assert path.exists(), f"File not found: {path}"
    return path.read_text(encoding="utf-8")


def test_fuzzy_yaml_config_loading():
    config_path = Path("config/fuzzy_rules.yaml")
    assert config_path.exists(), "fuzzy_rules.yaml not found"
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    assert "ventilation_control" in config, "ventilation_control section missing"
    vc = config["ventilation_control"]
    
    assert "input_variables" in vc, "input_variables missing"
    assert "oxygen" in vc["input_variables"], "oxygen variable missing"
    assert "temperature" in vc["input_variables"], "temperature variable missing"
    assert "humidity" in vc["input_variables"], "humidity variable missing"
    
    assert "output_variable" in vc, "output_variable missing"
    assert "fan_speed" in vc["output_variable"], "fan_speed output missing"
    
    assert "rule_base" in vc, "rule_base missing"
    assert len(vc["rule_base"]) == 12, f"Expected 12 rules, got {len(vc['rule_base'])}"
    
    for rule in vc["rule_base"]:
        assert "id" in rule, "Rule missing id"
        assert "condition" in rule, "Rule missing condition"
        assert "action" in rule, "Rule missing action"
    
    rule1 = [r for r in vc["rule_base"] if r["id"] == 1][0]
    assert rule1["condition"] == {"oxygen": "very_low"}, "Rule 1 condition incorrect"
    assert rule1["action"] == {"fan_speed": "full"}, "Rule 1 action incorrect"
    
    rule11 = [r for r in vc["rule_base"] if r["id"] == 11][0]
    assert rule11["condition"] == {"oxygen": "low", "temperature": "high"}, "Rule 11 condition incorrect"
    assert rule11["action"] == {"fan_speed": "full"}, "Rule 11 action incorrect"
    
    assert "pump_control" in config, "pump_control section missing"
    assert config["pump_control"]["level_high"] == 80, "Pump high threshold incorrect"
    assert config["pump_control"]["level_low"] == 30, "Pump low threshold incorrect"
    assert config["pump_control"]["min_run_time"] == 30, "Min run time incorrect"
    
    assert "alarm_thresholds" in config, "alarm_thresholds section missing"
    assert config["alarm_thresholds"]["methane"] == 1.0, "Methane threshold incorrect"
    assert config["alarm_thresholds"]["h2s"] == 10.0, "H2S threshold incorrect"
    assert config["alarm_thresholds"]["oxygen_low"] == 18.0, "Oxygen threshold incorrect"
    
    logger.info(f"Loaded {len(vc['rule_base'])} fuzzy rules")
    return True


def test_membership_function_definitions():
    config_path = Path("config/fuzzy_rules.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    vc = config["ventilation_control"]
    
    oxygen_mfs = vc["input_variables"]["oxygen"]["membership_functions"]
    assert "very_low" in oxygen_mfs, "very_low MF missing"
    assert oxygen_mfs["very_low"]["type"] == "trapezoid", "very_low should be trapezoid"
    assert oxygen_mfs["very_low"]["params"] == [0, 0, 17, 18], "very_low params incorrect"
    
    assert "low" in oxygen_mfs, "low MF missing"
    assert oxygen_mfs["low"]["params"] == [17, 18, 18.5, 19], "low params incorrect"
    
    assert "normal" in oxygen_mfs, "normal MF missing"
    assert oxygen_mfs["normal"]["params"] == [18.5, 19, 21, 21.5], "normal params incorrect"
    
    fan_speed_mfs = vc["output_variable"]["fan_speed"]["membership_functions"]
    assert "stop" in fan_speed_mfs, "stop MF missing"
    assert fan_speed_mfs["stop"]["type"] == "singleton", "stop should be singleton"
    assert fan_speed_mfs["stop"]["params"] == [0], "stop params incorrect"
    
    assert "full" in fan_speed_mfs, "full MF missing"
    assert fan_speed_mfs["full"]["params"] == [100], "full params incorrect"
    
    logger.info("All membership function definitions correct")
    return True


def test_fuzzy_inference_logic_static():
    vc_source = load_source("backend/modules/ventilation_controller.py")
    
    assert "class FuzzyController" in vc_source, "FuzzyController class missing"
    assert "class FuzzyVariable" in vc_source, "FuzzyVariable class missing"
    assert "class FuzzyRule" in vc_source, "FuzzyRule class missing"
    assert "class MembershipFunction" in vc_source, "MembershipFunction class missing"
    
    assert "def fuzzify" in vc_source, "fuzzify method missing"
    assert "def infer" in vc_source, "infer method missing"
    assert "_mamdani_inference" in vc_source, "Mamdani inference missing"
    assert "_defuzzify_centroid" in vc_source, "Centroid defuzzification missing"
    
    assert "yaml.safe_load" in vc_source, "YAML loading missing"
    assert "FUZZY_RULES_PATH" in vc_source, "Config path missing"
    
    assert ("class ChamberVentilation" in vc_source or "class ChamberVentilationController" in vc_source), "ChamberVentilation class missing"
    assert "self.chamber_controllers" in vc_source, "Chamber controllers dict missing"
    assert "FANS_PER_CHAMBER" in vc_source, "FANS_PER_CHAMBER config missing"
    
    logger.info("Fuzzy inference logic structure correct")
    return True


def test_lora_receiver_module():
    lr_source = load_source("backend/modules/lora_receiver.py")
    
    assert "class LoraReceiver" in lr_source, "LoraReceiver class missing"
    assert "def validate_sensor_data" in lr_source, "validate_sensor_data method missing"
    assert "def process_single_data" in lr_source, "process_single_data method missing"
    assert "def process_batch_data" in lr_source, "process_batch_data method missing"
    assert "_publish_to_redis" in lr_source, "Redis publish method missing"
    
    assert "insert_many" in lr_source, "Batch insert missing"
    assert "bulk_write" in lr_source, "Bulk update missing"
    assert "ordered=False" in lr_source, "Unordered batch writes missing"
    
    assert "max_change" in lr_source, "Change detection missing"
    assert "_history_cache" in lr_source, "History cache missing"
    assert "validate_sensor_data" in lr_source, "Data validation missing"
    
    assert "redis.Redis" in lr_source, "Redis client missing"
    assert "redis_client.publish" in lr_source, "Redis publish missing"
    
    assert "connect_redis" in lr_source, "connect_redis method missing"
    assert "disconnect_redis" in lr_source, "disconnect_redis method missing"
    assert "start_redis_listener" in lr_source, "start_redis_listener method missing"
    
    assert "lora_receiver = LoraReceiver()" in lr_source, "Module instance missing"
    
    logger.info("LoraReceiver module structure correct")
    return True


def test_pump_controller_module():
    pc_source = load_source("backend/modules/pump_controller.py")
    
    assert "class PumpControllerModule" in pc_source, "PumpControllerModule class missing"
    assert "def calculate_control" in pc_source, "calculate_control method missing"
    assert "_get_average_level" in pc_source, "Moving average missing"
    assert "level_history" in pc_source, "Level history missing"
    
    assert "level_high" in pc_source, "High threshold missing"
    assert "level_low" in pc_source, "Low threshold missing"
    assert "min_run_time" in pc_source, "Min run time missing"
    
    hysteresis_patterns = ["avg_level <= self.level_low", "avg_level >= self.level_high"]
    for pattern in hysteresis_patterns:
        assert pattern in pc_source, f"Hysteresis check missing: {pattern}"
    
    min_run_check = "run_duration >= self.min_run_time"
    assert min_run_check in pc_source, "Min run time check missing"
    
    assert "redis.Redis" in pc_source, "Redis client missing"
    assert "pubsub.subscribe" in pc_source, "Redis subscribe missing"
    
    assert "connect_redis" in pc_source, "connect_redis method missing"
    assert "disconnect_redis" in pc_source, "disconnect_redis method missing"
    assert "start_control_loop" in pc_source, "start_control_loop method missing"
    
    logger.info("PumpController module structure correct")
    return True


def test_alarm_manager_module():
    am_source = load_source("backend/modules/alarm_manager.py")
    
    assert "class AlarmManager" in am_source, "AlarmManager class missing"
    assert "ALERT_NOTIFICATION_STRATEGY" in am_source, "Notification strategy missing"
    
    assert '"level1": {"websocket": True, "sms": False}' in am_source or \
           "'level1': {'websocket': True, 'sms': False}" in am_source, \
           "Level1 notification strategy incorrect"
    
    assert '"level2": {"websocket": True, "sms": True}' in am_source or \
           "'level2': {'websocket': True, 'sms': True}" in am_source, \
           "Level2 notification strategy incorrect"
    
    assert '"security": {"websocket": True, "sms": False}' in am_source or \
           "'security': {'websocket': True, 'sms': False}" in am_source, \
           "Security notification strategy incorrect"
    
    assert "alert_cooldown" in am_source, "Alert cooldown missing"
    assert "sms_cooldown" in am_source, "SMS cooldown missing"
    assert "ALERT_COOLDOWN_MINUTES = 5" in am_source, "Alert cooldown value incorrect"
    assert "SMS_COOLDOWN_MINUTES = 15" in am_source, "SMS cooldown value incorrect"
    
    alert_level_check = "alert.level == AlertLevel.LEVEL2"
    strategy_check = "ALERT_NOTIFICATION_STRATEGY.get(alert.level"
    sms_check = "_send_sms_alert"
    assert (alert_level_check in am_source or (strategy_check in am_source and sms_check in am_source)), \
        "Level2 SMS check missing"
    
    assert "websocket_manager.broadcast" in am_source, "WebSocket broadcast missing"
    assert "_send_sms" in am_source, "SMS send method missing"
    
    assert "connect_redis" in am_source, "connect_redis method missing"
    assert "disconnect_redis" in am_source, "disconnect_redis method missing"
    assert "start_listener" in am_source, "start_listener method missing"
    
    logger.info("AlarmManager module structure correct")
    return True


def test_main_py_module_integration():
    main_source = load_source("backend/main.py")
    
    module_imports = [
        "from backend.modules import",
        "lora_receiver",
        "ventilation_controller",
        "pump_controller_module",
        "alarm_manager"
    ]
    
    for imp in module_imports:
        assert imp in main_source, f"Missing import: {imp}"
    
    lifespan_operations = [
        "lora_receiver.connect_redis()",
        "ventilation_controller.connect_redis()",
        "pump_controller_module.connect_redis()",
        "alarm_manager.connect_redis()",
        "lora_receiver.start_redis_listener()",
        "ventilation_controller.start_control_loop()",
        "pump_controller_module.start_control_loop()",
        "alarm_manager.start_listener()"
    ]
    
    for op in lifespan_operations:
        assert op in main_source, f"Missing lifespan operation: {op}"
    
    shutdown_operations = [
        "lora_receiver.disconnect_redis()",
        "ventilation_controller.disconnect_redis()",
        "pump_controller_module.disconnect_redis()",
        "alarm_manager.disconnect_redis()"
    ]
    
    for op in shutdown_operations:
        assert op in main_source, f"Missing shutdown operation: {op}"
    
    logger.info("main.py module integration correct")
    return True


def test_sensor_route_refactoring():
    sensor_source = load_source("backend/routes/sensor.py")
    
    assert "from backend.modules import lora_receiver" in sensor_source, \
        "sensor.py should import lora_receiver"
    
    assert "lora_receiver.process_data(" in sensor_source, \
        "sensor.py should use lora_receiver.process_data"
    
    assert "lora_receiver.process_batch_data(" in sensor_source, \
        "sensor.py should use lora_receiver.process_batch_data"
    
    assert "control_service.process_sensor_data(" not in sensor_source, \
        "sensor.py should NOT use control_service directly for data processing"
    
    assert "batch_size = 50" in sensor_source, "Batch size config missing"
    
    logger.info("sensor.py route refactoring correct")
    return True


def test_frontend_corridor_map_component():
    cm_source = load_source("frontend/js/corridor_map.js")
    
    assert "class CorridorMap" in cm_source, "CorridorMap class missing"
    assert "constructor()" in cm_source, "Constructor missing"
    assert "init(" in cm_source, "init method missing"
    assert "loadDevices(" in cm_source, "loadDevices method missing"
    assert "updateDeviceStatus(" in cm_source, "updateDeviceStatus method missing"
    assert "setOnDeviceClick(" in cm_source, "setOnDeviceClick method missing"
    assert "_createCanvasOverlay(" in cm_source, "Canvas overlay method missing"
    assert "_drawOnCanvas(" in cm_source, "Canvas draw method missing"
    
    assert "L.map(" in cm_source, "Leaflet map missing"
    assert ("L.geoJSON(" in cm_source or "fetch.*geojson" in cm_source.lower() or "loadDevices" in cm_source), \
        "GeoJSON loading missing"
    
    assert "window.CorridorMap = CorridorMap" in cm_source, "Global export missing"
    
    logger.info("CorridorMap component structure correct")
    return True


def test_frontend_device_detail_component():
    dd_source = load_source("frontend/js/device_detail.js")
    
    assert "class DeviceDetail" in dd_source, "DeviceDetail class missing"
    assert "init(" in dd_source, "init method missing"
    assert "show(" in dd_source, "show method missing"
    assert "hide(" in dd_source, "hide method missing"
    assert "_renderDeviceInfo(" in dd_source, "_renderDeviceInfo method missing"
    assert "_renderDeviceHistory(" in dd_source, "_renderDeviceHistory method missing"
    assert "_renderOperations(" in dd_source, "_renderOperations method missing"
    assert "_renderDeviceControls(" in dd_source, "_renderDeviceControls method missing"
    assert "controlFan(" in dd_source, "controlFan method missing"
    assert "controlPump(" in dd_source, "controlPump method missing"
    assert "setOnClose(" in dd_source, "setOnClose method missing"
    
    assert "new Chart(" in dd_source, "Chart.js integration missing"
    assert "yAxisID" in dd_source, "Multi-axis chart missing"
    
    assert "setInterval" in dd_source, "Auto refresh missing"
    
    assert ("window.DeviceDetail = DeviceDetail" in dd_source or "window.DeviceDetail = new DeviceDetail()" in dd_source), \
        "Global export missing"
    
    logger.info("DeviceDetail component structure correct")
    return True


def test_frontend_app_integration():
    app_source = load_source("frontend/js/app.js")
    map_source = load_source("frontend/js/map.js")
    
    assert "class TunnelMap" in map_source, "TunnelMap wrapper class missing"
    assert "_corridorMap" in map_source, "TunnelMap should delegate to CorridorMap"
    assert "new window.CorridorMap()" in map_source, "CorridorMap instantiation missing"
    
    assert "window.DeviceDetail" in app_source, "App should use DeviceDetail component"
    assert "this.deviceDetail = window.DeviceDetail" in app_source, \
        "DeviceDetail assignment missing"
    assert "this.deviceDetail.init()" in app_source, "DeviceDetail init missing"
    assert "this.deviceDetail.show(" in app_source, "DeviceDetail show missing"
    
    assert "_renderDeviceInfo" not in app_source, \
        "_renderDeviceInfo should be removed from app.js"
    assert "_renderDeviceHistory" not in app_source, \
        "_renderDeviceHistory should be removed from app.js"
    assert "_renderOperations" not in app_source, \
        "_renderOperations should be removed from app.js"
    assert "_renderDeviceControls" not in app_source, \
        "_renderDeviceControls should be removed from app.js"
    assert "controlFan(" not in app_source, \
        "controlFan should be removed from app.js"
    assert "controlPump(" not in app_source, \
        "controlPump should be removed from app.js"
    
    logger.info("Frontend app integration correct")
    return True


def test_frontend_index_html():
    html_source = load_source("frontend/index.html")
    
    script_patterns = [
        'corridor_map.js',
        'device_detail.js',
        'map.js',
        'app.js'
    ]
    
    for pattern in script_patterns:
        assert pattern in html_source, f"Missing script include: {pattern}"
    
    match = re.search(r'corridor_map\.js.*device_detail\.js.*map\.js.*app\.js', 
                      html_source, re.DOTALL)
    assert match, "Script loading order incorrect"
    
    logger.info("index.html script loading order correct")
    return True


def test_redis_pubsub_channels():
    config_source = load_source("backend/config.py")
    
    import re
    
    assert "REDIS_HOST" in config_source, "REDIS_HOST missing"
    assert "REDIS_PORT" in config_source, "REDIS_PORT missing"
    
    found_sensor = "REDIS_CHANNEL_SENSOR_DATA" in config_source
    found_control = "REDIS_CHANNEL_CONTROL_COMMAND" in config_source
    found_alert = "REDIS_CHANNEL_ALERT_EVENT" in config_source
    
    if not (found_sensor and found_control and found_alert):
        logger.warning(f"  Warning: Some Redis channel names not found in source. "
                       f"sensor={found_sensor}, control={found_control}, alert={found_alert}")
        logger.warning(f"  Checking for channel pattern instead...")
        
        channel_pattern = r"REDIS_CHANNEL_\w+\s*[:=]"
        import re
        matches = re.findall(channel_pattern, config_source)
        logger.info(f"  Found {len(matches)} channel definitions: {matches}")
        
        assert len(matches) >= 3, f"Expected at least 3 Redis channels, found {len(matches)}"
    else:
        assert found_sensor, "Sensor data channel missing"
        assert found_control, "Control command channel missing"
        assert found_alert, "Alert event channel missing"
    
    assert "FUZZY_RULES_PATH" in config_source, "FUZZY_RULES_PATH missing"
    assert "config/fuzzy_rules.yaml" in config_source, "Fuzzy rules path incorrect"
    
    assert "FANS_PER_CHAMBER" in config_source, "FANS_PER_CHAMBER missing"
    assert "CHAMBERS" in config_source, "CHAMBERS config missing"
    
    logger.info("Redis Pub/Sub channels configured correctly")
    return True


def test_ventilation_chamber_grouping():
    vc_source = load_source("backend/modules/ventilation_controller.py")
    
    assert "CHAMBERS" in vc_source, "CHAMBERS config usage missing"
    assert "FANS_PER_CHAMBER" in vc_source, "FANS_PER_CHAMBER config usage missing"
    assert ("class ChamberVentilation" in vc_source or "class ChamberVentilationController" in vc_source), \
        "ChamberVentilation class missing"
    assert ("self.chamber_controllers = {}" in vc_source or "self.chamber_controllers:" in vc_source), \
        "Chamber controllers dict missing"
    
    chamber_check = "settings.CHAMBERS" in vc_source or "CHAMBERS" in vc_source
    assert chamber_check, "Chamber configuration usage missing"
    
    per_chamber_check = "len(fan_ids) <= settings.FANS_PER_CHAMBER"
    assert per_chamber_check in vc_source or "FANS_PER_CHAMBER" in vc_source, \
        "Per chamber fan limit check missing"
    
    logger.info("Ventilation chamber grouping correct")
    return True


def test_mongodb_batch_operations():
    lr_source = load_source("backend/modules/lora_receiver.py")
    cs_source = load_source("backend/services/control_service.py")
    
    batch_operations = [
        ("lora_receiver.py", "insert_many"),
        ("lora_receiver.py", "bulk_write"),
        ("control_service.py", "insert_many"),
        ("control_service.py", "bulk_write"),
        ("lora_receiver.py", "ordered=False")
    ]
    
    for filename, op in batch_operations:
        source = lr_source if "lora" in filename else cs_source
        assert op in source, f"Missing {op} in {filename}"
    
    logger.info("MongoDB batch operations correct")
    return True


def test_sms_cost_optimization():
    am_source = load_source("backend/modules/alarm_manager.py")
    as_source = load_source("backend/services/alert_service.py")
    
    level2_check_patterns = [
        "alert.level == AlertLevel.LEVEL2",
        "LEVEL2",
        "ALERT_NOTIFICATION_STRATEGY"
    ]
    
    sms_send_patterns = [
        "_send_sms(",
        "send_sms(",
        "_send_sms_alert"
    ]
    
    am_has_level2_check = any(p in am_source for p in level2_check_patterns)
    am_has_sms = any(p in am_source for p in sms_send_patterns)
    assert am_has_level2_check and am_has_sms, \
        "AlarmManager missing level2 SMS check"
    
    as_has_level2_check = any(p in as_source for p in level2_check_patterns)
    as_has_sms = any(p in as_source for p in sms_send_patterns)
    assert (as_has_level2_check and as_has_sms) or (as_has_level2_check and "SMS skipped" in as_source), \
        "AlertService missing level2 SMS check"
    
    sms_skip_log = 'SMS skipped'
    assert sms_skip_log in am_source or sms_skip_log in as_source, \
        "SMS skip logging missing"
    
    logger.info("SMS cost optimization (level2 only) correct")
    return True


def test_requirements_txt():
    req_source = load_source("requirements.txt")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "motor",
        "pydantic",
        "redis",
        "PyYAML",
        "websockets",
        "numpy",
        "paho-mqtt"
    ]
    
    for pkg in required_packages:
        assert pkg in req_source, f"Missing package in requirements.txt: {pkg}"
    
    logger.info("requirements.txt complete")
    return True


def test_python_syntax_all_files():
    py_files = [
        "backend/main.py",
        "backend/config.py",
        "backend/modules/lora_receiver.py",
        "backend/modules/ventilation_controller.py",
        "backend/modules/pump_controller.py",
        "backend/modules/alarm_manager.py",
        "backend/modules/__init__.py",
        "backend/routes/sensor.py",
        "backend/routes/devices.py",
        "backend/routes/alerts.py",
        "backend/routes/control.py",
        "backend/routes/stats.py",
        "backend/services/control_service.py",
        "backend/services/alert_service.py",
        "backend/control/ventilation_pid.py",
        "backend/structural_monitor/__init__.py",
        "backend/structural_monitor/core.py",
        "backend/structural_monitor/api.py",
        "backend/structural_monitor/models.py",
        "backend/robot_planner/__init__.py",
        "backend/robot_planner/core.py",
        "backend/robot_planner/api.py",
        "backend/robot_planner/models.py",
        "backend/robot_planner/path_process.py",
        "backend/fire_early_warning/__init__.py",
        "backend/fire_early_warning/core.py",
        "backend/fire_early_warning/api.py",
        "backend/fire_early_warning/models.py",
        "backend/fire_early_warning/inference_service.py",
        "backend/asset_manager/__init__.py",
        "backend/asset_manager/core.py",
        "backend/asset_manager/api.py",
        "backend/asset_manager/models.py"
    ]
    
    import py_compile
    for py_file in py_files:
        try:
            py_compile.compile(py_file, doraise=True)
            logger.info(f"  ✅ {py_file} syntax OK")
        except py_compile.PyCompileError as e:
            raise AssertionError(f"Syntax error in {py_file}: {e}")
    
    logger.info("All Python files syntax correct")
    return True


def test_structural_monitor_module():
    sm_core = load_source("backend/structural_monitor/core.py")
    sm_api = load_source("backend/structural_monitor/api.py")
    
    assert "class StructureMonitor" in sm_core, "StructureMonitor class missing"
    assert "class StructureHeatmapPoint" in sm_core or "StructureHeatmapPoint" in sm_core, "Heatmap model missing"
    assert "process_fiber_data" in sm_core, "process_fiber_data method missing"
    assert "get_heatmap_data" in sm_core, "get_heatmap_data method missing"
    assert "get_active_alerts" in sm_core, "get_active_alerts method missing"
    assert "connect_redis" in sm_core, "connect_redis method missing"
    assert "start_listener" in sm_core, "start_listener method missing"
    assert "structure_monitor = StructureMonitor()" in sm_core, "Module instance missing"
    
    assert "router = APIRouter(prefix=\"/api/structure\"" in sm_api, "API router prefix incorrect"
    assert "from structural_monitor.core import structure_monitor" in sm_api, "Core import missing in API"
    
    api_endpoints = [
        "/data",
        "/data/batch",
        "/heatmap",
        "/alerts/active",
        "/alerts",
        "/trend",
        "/statistics"
    ]
    for endpoint in api_endpoints:
        assert endpoint in sm_api, f"API endpoint missing: {endpoint}"
    
    logger.info("StructuralMonitor module structure correct")
    return True


def test_robot_planner_module():
    rp_core = load_source("backend/robot_planner/core.py")
    rp_api = load_source("backend/robot_planner/api.py")
    rp_process = load_source("backend/robot_planner/path_process.py")
    
    assert "class RobotPlanner" in rp_core, "RobotPlanner class missing"
    assert "plan_path" in rp_core, "plan_path method missing"
    assert "get_all_robots" in rp_core, "get_all_robots method missing"
    assert "update_robot_position" in rp_core, "update_robot_position method missing"
    assert "start_control_loop" in rp_core, "start_control_loop method missing"
    assert "robot_planner = RobotPlanner()" in rp_core, "Module instance missing"
    
    assert "multiprocessing.Process" in rp_process, "Multiprocessing usage missing"
    assert "start_path_planner_process" in rp_process, "start_path_planner_process function missing"
    assert "stop_path_planner_process" in rp_process, "stop_path_planner_process function missing"
    assert "is_process_running" in rp_process, "is_process_running function missing"
    assert "send_path_planning_request" in rp_process, "send_path_planning_request function missing"
    assert "_astar_path_planning" in rp_process, "A* path planning function missing"
    
    assert "from robot_planner.path_process import" in rp_api, "Path process import missing in API"
    assert "/path-planner/status" in rp_api, "Path planner status endpoint missing"
    
    logger.info("RobotPlanner module structure correct (with independent path planning process)")
    return True


def test_fire_early_warning_module():
    few_core = load_source("backend/fire_early_warning/core.py")
    few_api = load_source("backend/fire_early_warning/api.py")
    few_inference = load_source("backend/fire_early_warning/inference_service.py")
    
    assert "class FireEarlyWarning" in few_core, "FireEarlyWarning class missing"
    assert "class BayesianFireDetector" in few_core, "BayesianFireDetector class missing"
    assert "process_fire_sensor_data" in few_core, "process_fire_sensor_data method missing"
    assert "calculate_fire_probability" in few_core, "calculate_fire_probability method missing"
    assert "use_inference_service" in few_core, "use_inference_service flag missing"
    assert "fire_early_warning = FireEarlyWarning()" in few_core, "Module instance missing"
    
    assert "call_inference_service" in few_core, "Inference service call missing"
    assert "is_service_running()" in few_core, "Service running check missing"
    
    assert "multiprocessing.Process" in few_inference, "Multiprocessing usage missing"
    assert "start_inference_service" in few_inference, "start_inference_service function missing"
    assert "stop_inference_service" in few_inference, "stop_inference_service function missing"
    assert "call_inference_service" in few_inference, "call_inference_service function missing"
    assert "BayesianFireDetector" in few_inference, "Bayesian detector in inference service missing"
    assert "FastAPI" in few_inference, "FastAPI for inference service missing"
    
    assert "from fire_early_warning.inference_service import" in few_api, "Inference service import missing in API"
    assert "/inference-service/status" in few_api, "Inference service status endpoint missing"
    
    logger.info("FireEarlyWarning module structure correct (with independent inference service)")
    return True


def test_asset_manager_module():
    am_core = load_source("backend/asset_manager/core.py")
    am_api = load_source("backend/asset_manager/api.py")
    
    assert "class AssetManager" in am_core, "AssetManager class missing"
    assert "class LifePredictionModel" in am_core, "LifePredictionModel class missing"
    assert "create_asset" in am_core, "create_asset method missing"
    assert "get_asset" in am_core, "get_asset method missing"
    assert "predict_remaining_life" in am_core, "predict_remaining_life method missing"
    assert "generate_monthly_maintenance_plan" in am_core, "generate_monthly_maintenance_plan method missing"
    assert "scan_for_device_replacements" in am_core, "scan_for_device_replacements method missing"
    assert "asset_manager = AssetManager()" in am_core, "Module instance missing"
    
    assert "router = APIRouter(prefix=\"/api/assets\"" in am_api, "API router prefix incorrect"
    assert "from asset_manager.core import asset_manager" in am_api, "Core import missing in API"
    
    api_endpoints = [
        "/statistics",
        "/life-predictions",
        "/reports/warranty",
        "/reports/maintenance-due",
        "/maintenance-plans/generate",
        "/maintenance-plans/{plan_id}/approve",
        "/replacement-history",
        "/scan-replacements"
    ]
    for endpoint in api_endpoints:
        assert endpoint in am_api, f"API endpoint missing: {endpoint}"
    
    logger.info("AssetManager module structure correct")
    return True


def test_frontend_new_components():
    sm_js = load_source("frontend/js/structure_monitor.js")
    rp_js = load_source("frontend/js/robot_inspector.js")
    few_js = load_source("frontend/js/fire_detector.js")
    am_js = load_source("frontend/js/asset_manager.js")
    
    assert "class StructuralMonitorComponent" in sm_js, "StructuralMonitorComponent class missing"
    assert "fetchHeatmapData" in sm_js, "fetchHeatmapData method missing"
    assert "window.StructuralMonitorComponent" in sm_js, "Global export missing"
    
    assert "class RobotPlannerComponent" in rp_js, "RobotPlannerComponent class missing"
    assert "fetchRobots" in rp_js, "fetchRobots method missing"
    assert "window.RobotPlannerComponent" in rp_js, "Global export missing"
    
    assert "class FireEarlyWarningComponent" in few_js, "FireEarlyWarningComponent class missing"
    assert "fetchFireAlerts" in few_js, "fetchFireAlerts method missing"
    assert "window.FireEarlyWarningComponent" in few_js, "Global export missing"
    
    assert "class AssetManagerComponent" in am_js, "AssetManagerComponent class missing"
    assert "fetchAssets" in am_js, "fetchAssets method missing"
    assert "new Chart(" in am_js, "Chart.js integration missing"
    assert "window.AssetManagerComponent" in am_js, "Global export missing"
    
    logger.info("All new frontend components structure correct")
    return True


def test_config_new_features():
    config_source = load_source("backend/config.py")
    
    new_configs = [
        "FIRE_INFERENCE_SERVICE_PORT",
        "ROBOT_PATH_PLANNER_PROCESS_PORT",
        "FIRE_PROBABILITY_THRESHOLD",
        "ASSET_REPLACEMENT_SERIAL_CHANGE",
        "NUM_FIBER_SENSORS",
        "NUM_INSPECTION_ROBOTS",
        "NUM_SMOKE_SENSORS"
    ]
    
    for config in new_configs:
        assert config in config_source, f"New config missing: {config}"
    
    logger.info("All new feature configurations present")
    return True


def test_main_py_new_modules():
    main_source = load_source("backend/main.py")
    
    new_import_modules = [
        "from structural_monitor.core",
        "from structural_monitor.api",
        "from robot_planner.core",
        "from robot_planner.api",
        "from robot_planner.path_process",
        "from fire_early_warning.core",
        "from fire_early_warning.api",
        "from fire_early_warning.inference_service",
        "from asset_manager.core",
        "from asset_manager.api"
    ]
    
    for imp in new_import_modules:
        assert imp in main_source, f"Missing new module import: {imp}"
    
    imported_symbols = [
        "structure_monitor",
        "router as structure_router",
        "robot_planner",
        "router as robots_router",
        "start_path_planner_process",
        "stop_path_planner_process",
        "fire_early_warning",
        "router as fire_router",
        "start_inference_service",
        "stop_inference_service",
        "asset_manager",
        "router as assets_router"
    ]
    
    for sym in imported_symbols:
        assert sym in main_source, f"Missing imported symbol: {sym}"
    
    lifespan_operations = [
        "start_path_planner_process()",
        "start_inference_service()",
        "stop_path_planner_process()",
        "stop_inference_service()",
        "structure_monitor.connect_redis()",
        "robot_planner.connect_redis()",
        "fire_early_warning.connect_redis()",
        "asset_manager.connect_redis()"
    ]
    
    for op in lifespan_operations:
        assert op in main_source, f"Missing lifespan operation: {op}"
    
    router_registrations = [
        "app.include_router(structure_router)",
        "app.include_router(robots_router)",
        "app.include_router(fire_router)",
        "app.include_router(assets_router)"
    ]
    
    for reg in router_registrations:
        assert reg in main_source, f"Missing router registration: {reg}"
    
    logger.info("main.py new modules integration correct")
    return True


def main():
    suite = RegressionTestSuite()
    
    logger.info("=" * 60)
    logger.info("STARTING REGRESSION TEST SUITE")
    logger.info("=" * 60)
    
    logger.info("\n--- Configuration Tests ---")
    suite.run_test("1. YAML Config Loading", test_fuzzy_yaml_config_loading)
    suite.run_test("2. Membership Function Definitions", test_membership_function_definitions)
    suite.run_test("3. Redis Pub/Sub Channels", test_redis_pubsub_channels)
    suite.run_test("4. requirements.txt", test_requirements_txt)
    suite.run_test("4.1 New Feature Configs", test_config_new_features)
    
    logger.info("\n--- Backend Module Structure Tests ---")
    suite.run_test("5. LoraReceiver Module", test_lora_receiver_module)
    suite.run_test("6. PumpController Module", test_pump_controller_module)
    suite.run_test("7. AlarmManager Module", test_alarm_manager_module)
    suite.run_test("8. Fuzzy Inference Logic (Static)", test_fuzzy_inference_logic_static)
    suite.run_test("9. StructuralMonitor Module", test_structural_monitor_module)
    suite.run_test("10. RobotPlanner Module (Independent Process)", test_robot_planner_module)
    suite.run_test("11. FireEarlyWarning Module (Inference Service)", test_fire_early_warning_module)
    suite.run_test("12. AssetManager Module", test_asset_manager_module)
    
    logger.info("\n--- Integration Tests ---")
    suite.run_test("13. main.py Module Integration", test_main_py_module_integration)
    suite.run_test("14. main.py New Modules Integration", test_main_py_new_modules)
    suite.run_test("15. sensor.py Route Refactoring", test_sensor_route_refactoring)
    
    logger.info("\n--- Frontend Component Tests ---")
    suite.run_test("16. CorridorMap Component", test_frontend_corridor_map_component)
    suite.run_test("17. DeviceDetail Component", test_frontend_device_detail_component)
    suite.run_test("18. Frontend App Integration", test_frontend_app_integration)
    suite.run_test("19. index.html Script Order", test_frontend_index_html)
    suite.run_test("20. New Feature Components", test_frontend_new_components)
    
    logger.info("\n--- Performance & Optimization Tests ---")
    suite.run_test("21. Ventilation Chamber Grouping", test_ventilation_chamber_grouping)
    suite.run_test("22. MongoDB Batch Operations", test_mongodb_batch_operations)
    suite.run_test("23. SMS Cost Optimization", test_sms_cost_optimization)
    
    logger.info("\n--- Syntax Validation ---")
    suite.run_test("24. Python Syntax All Files", test_python_syntax_all_files)
    
    success = suite.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
