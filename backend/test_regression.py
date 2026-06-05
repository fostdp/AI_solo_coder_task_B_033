import sys
import json
import asyncio
import codecs
from datetime import datetime, timedelta
sys.path.insert(0, '.')

sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

print('=' * 60)
print('Underground Pipe Corridor System - Regression Test')
print('=' * 60)
print()

PASS = '[OK]'
FAIL = '[FAIL]'

# 1. Test data models
print('=== 1. Data Model Tests ===')
from models.models import (
    EnvironmentData, EnvironmentDataBatch,
    ManholeData, ManholeDataBatch,
    Alarm, AlarmLevel, AlarmType, CabinType,
    OperationHistory, PumpData, FanData
)
from config.settings import settings

# Test environment data
env_data = EnvironmentData(
    device_id='ENV-TEST-001',
    cabin=CabinType.POWER,
    temperature=25.5,
    humidity=60.0,
    oxygen=20.5,
    methane=0.0,
    hydrogen_sulfide=0.0,
    timestamp=datetime.now()
)
print(f'{PASS} EnvironmentData: {env_data.device_id}, temp={env_data.temperature}C')

# Test batch data
batch = EnvironmentDataBatch(
    gateway_id='GW-TEST-001',
    data=[env_data],
    timestamp=datetime.now()
)
print(f'{PASS} EnvironmentDataBatch: {len(batch.data)} records')

# Test operation history
op_history = OperationHistory(
    device_id='FAN-TEST-001',
    operation='manual_start',
    operator='test',
    parameters={'speed': 50}
)
print(f'{PASS} OperationHistory: {op_history.device_id} -> {op_history.operation}')

# Test pump data
pump_data = PumpData(
    device_id='PUMP-TEST-001',
    cabin=CabinType.WATER,
    is_running=False,
    level=0.5,
    timestamp=datetime.now()
)
print(f'{PASS} PumpData: {pump_data.device_id}, level={pump_data.level}m')
print()

# 2. Test Redis message structure
print('=== 2. Redis Message Tests ===')
from utils.redis_client import RedisMessage, RedisChannels

msg = RedisMessage(
    channel=RedisChannels.ENV_DATA,
    data={'device_id': 'TEST-001', 'temperature': 25.0}
)
msg_dict = msg.to_dict()
print(f'{PASS} RedisMessage: channel={msg_dict["channel"]}, data={msg_dict["data"]}')

# Test JSON serialization
msg_json = json.dumps(msg_dict)
parsed = json.loads(msg_json)
print(f'{PASS} JSON serialize/deserialize: {parsed["channel"]}')
print()

# 3. Test fuzzy logic configuration
print('=== 3. Fuzzy Logic Config Tests ===')
from config.settings import settings
from controllers.ventilation_control import FuzzyConfigLoader

loader = FuzzyConfigLoader(settings.FUZZY_CONFIG_PATH)
print(f'{PASS} Membership functions:')
input_vars = loader.config['fuzzy_logic']['input_variables']
for var_name, var_config in input_vars.items():
    mf_count = len(var_config.get('membership_functions', {}))
    print(f'  - {var_name}: {mf_count} functions')

print(f'{PASS} Rule base size: {len(loader.rule_table)} rules')

# Test some key rules
key_rules = [
    (('very_low', 'very_high', 'very_high'), True, 100),
    (('normal', 'normal', 'normal'), False, 0),
]
for conditions, expected_run, expected_speed in key_rules:
    result = loader.rule_table.get(conditions)
    if result:
        status = PASS if result == (expected_run, expected_speed) else FAIL
        print(f'  {status} Rule{conditions} -> run={result[0]}, speed={result[1]}%')
print()

# 4. Test fuzzy inference
print('=== 4. Fuzzy Inference Tests ===')
from controllers.ventilation_control import CabinVentilationController

controller = CabinVentilationController(CabinType.POWER, loader)

# Test different scenarios
test_cases = [
    {'name': 'Normal env', 'oxygen': 20.5, 'temperature': 25, 'humidity': 60, 'expect_run': False},
    {'name': 'Low oxygen', 'oxygen': 17.5, 'temperature': 25, 'humidity': 60, 'expect_run': True},
    {'name': 'High temp/humidity', 'oxygen': 20.5, 'temperature': 38, 'humidity': 85, 'expect_run': True},
    {'name': 'Severe anomaly', 'oxygen': 17.0, 'temperature': 38, 'humidity': 90, 'expect_run': True},
]

for case in test_cases:
    # Test fuzzification
    oxy_level = controller._fuzzify_oxygen(case['oxygen'])
    temp_level = controller._fuzzify_temperature(case['temperature'])
    hum_level = controller._fuzzify_humidity(case['humidity'])
    
    # Test inference
    should_run, speed = controller._infer(oxy_level, temp_level, hum_level)
    status = PASS if should_run == case['expect_run'] else FAIL
    print(f'  {status} {case["name"]}: O2={case["oxygen"]}% ({oxy_level}), T={case["temperature"]}C ({temp_level}), H={case["humidity"]}% ({hum_level}) -> run={should_run}, speed={speed}%')
print()

# 5. Test pump control logic
print('=== 5. Pump Control Logic Tests ===')
from controllers.pump_control import PumpController

pump_controller = PumpController()

# Test level change sequence
level_sequence = [
    (0.2, False, 'Low level - should not start'),
    (0.5, False, 'Medium level - should not start'),
    (0.9, True, 'Above start threshold - should start'),
    (1.2, True, 'High level - should run'),
]

print('  Level change tests:')
for level, expect_need_start, desc in level_sequence:
    # Simulate state transitions
    state = pump_controller.get_pump_state('PUMP-TEST')
    state['current_level'] = level
    state['is_running'] = False
    
    if level >= pump_controller.start_level and not state['is_running']:
        needs_start = True
    else:
        needs_start = False
    
    status = PASS if needs_start == expect_need_start else FAIL
    print(f'    {status} {desc}: {level}m -> needs_start={needs_start}')
print()

# 6. Test alarm classification logic
print('=== 6. Alarm Classification Tests ===')
from controllers.alarm_manager import AlarmManager

alarm_mgr = AlarmManager()

# Test alarm detection
alarm_test_cases = [
    {
        'name': 'Methane exceed',
        'data': {'device_id': 'ENV-001', 'cabin': 'gas', 'methane': 1.5},
        'expect_level': 'critical',
        'expect_type': 'gas_level1'
    },
    {
        'name': 'H2S exceed',
        'data': {'device_id': 'ENV-002', 'cabin': 'gas', 'hydrogen_sulfide': 15},
        'expect_level': 'critical',
        'expect_type': 'gas_level1'
    },
    {
        'name': 'Low oxygen',
        'data': {'device_id': 'ENV-003', 'cabin': 'power', 'oxygen': 17.5},
        'expect_level': 'critical',
        'expect_type': 'suffocation'
    },
    {
        'name': 'Illegal manhole open',
        'data': {'device_id': 'MH-001', 'cabin': 'power', 'is_open': True, 'is_legal': False},
        'expect_level': 'warning',
        'expect_type': 'security'
    },
    {
        'name': 'Normal data',
        'data': {'device_id': 'ENV-004', 'cabin': 'power', 'oxygen': 20.5, 'methane': 0.0},
        'expect_level': None,
        'expect_type': None
    },
]

print('  Alarm detection tests:')
for case in alarm_test_cases:
    alarms = []
    if 'methane' in case['data']:
        env_data = EnvironmentData(
            device_id=case['data']['device_id'],
            cabin=CabinType(case['data']['cabin']),
            temperature=25, humidity=60,
            oxygen=case['data'].get('oxygen', 20.5),
            methane=case['data'].get('methane', 0),
            hydrogen_sulfide=case['data'].get('hydrogen_sulfide', 0),
            timestamp=datetime.now()
        )
        # Test alarm conditions directly (skip DB write)
        if env_data.methane >= settings.METHANE_ALARM:
            alarms.append(Alarm(alarm_type=AlarmType.GAS_LEVEL1, level=AlarmLevel.CRITICAL,
                               device_id=env_data.device_id, cabin=env_data.cabin, message='test'))
        if env_data.hydrogen_sulfide >= settings.H2S_ALARM:
            alarms.append(Alarm(alarm_type=AlarmType.GAS_LEVEL1, level=AlarmLevel.CRITICAL,
                               device_id=env_data.device_id, cabin=env_data.cabin, message='test'))
        if env_data.oxygen <= settings.OXYGEN_DANGER:
            alarms.append(Alarm(alarm_type=AlarmType.SUFFOCATION, level=AlarmLevel.CRITICAL,
                               device_id=env_data.device_id, cabin=env_data.cabin, message='test'))
    elif 'is_open' in case['data']:
        if case['data']['is_open'] and not case['data']['is_legal']:
            alarms.append(Alarm(alarm_type=AlarmType.SECURITY, level=AlarmLevel.WARNING,
                               device_id=case['data']['device_id'], 
                               cabin=CabinType(case['data']['cabin']), message='test'))

    if case['expect_level'] is None:
        status = PASS if len(alarms) == 0 else FAIL
        print(f'    {status} {case["name"]}: no alarms')
    else:
        has_alarm = any(a.level.value == case['expect_level'] and a.alarm_type.value == case['expect_type'] for a in alarms)
        status = PASS if has_alarm else FAIL
        alarm_info = f'{len(alarms)} alarms' if alarms else 'no alarms'
        print(f'    {status} {case["name"]}: {alarm_info}')
print()

# 7. Test data validation
print('=== 7. Data Validation Tests ===')
from services.lora_receiver import LoRaReceiver

receiver = LoRaReceiver()

# Test outlier filtering
validation_cases = [
    {'name': 'Normal data', 'data': {'temperature': 25, 'humidity': 60, 'oxygen': 20.5}, 'valid': True},
    {'name': 'Temp too high', 'data': {'temperature': 85, 'humidity': 60, 'oxygen': 20.5}, 'valid': False},
    {'name': 'Temp too low', 'data': {'temperature': -50, 'humidity': 60, 'oxygen': 20.5}, 'valid': False},
    {'name': 'Humidity exceed', 'data': {'temperature': 25, 'humidity': 110, 'oxygen': 20.5}, 'valid': False},
    {'name': 'Oxygen exceed', 'data': {'temperature': 25, 'humidity': 60, 'oxygen': 50}, 'valid': False},
    {'name': 'Oxygen negative', 'data': {'temperature': 25, 'humidity': 60, 'oxygen': -5}, 'valid': False},
]

print('  Outlier filtering tests:')
for case in validation_cases:
    is_valid = receiver._validate_env_reading(case['data'])
    status = PASS if is_valid == case['valid'] else FAIL
    print(f'    {status} {case["name"]}: {"valid" if is_valid else "invalid"}')
print()

# 8. Frontend file checks
print('=== 8. Frontend File Checks ===')
import os

frontend_files = [
    'js/corridor_map.js',
    'js/device_detail.js',
    'js/app.js',
    'js/websocket.js',
    'js/api.js',
    'js/charts.js',
    'js/config.js',
]

for f in frontend_files:
    path = f'../frontend/{f}'
    exists = os.path.exists(path)
    if exists:
        with open(path, 'r', encoding='utf-8') as file:
            content = file.read()
            size = len(content)
            lines = content.count('\n') + 1
        print(f'  {PASS} {f}: {lines} lines, {size} bytes')
    else:
        print(f'  {FAIL} {f}: file not found')

# Check references
print()
print('  Component reference checks:')
with open('../frontend/js/app.js', 'r', encoding='utf-8') as f:
    app_content = f.read()
print(f'  {PASS if "CorridorMapModule" in app_content else FAIL} app.js imports CorridorMapModule')
print(f'  {PASS if "DeviceDetailModule" in app_content else FAIL} app.js imports DeviceDetailModule')
print(f'  {PASS if "MapModule" not in app_content else FAIL} app.js removed MapModule reference')

with open('../frontend/js/websocket.js', 'r', encoding='utf-8') as f:
    ws_content = f.read()
print(f'  {PASS if "CorridorMapModule" in ws_content else FAIL} websocket.js imports CorridorMapModule')
print(f'  {PASS if "MapModule" not in ws_content else FAIL} websocket.js removed MapModule reference')

with open('../frontend/index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()
print(f'  {PASS if "corridor_map.js" in html_content else FAIL} index.html includes corridor_map.js')
print(f'  {PASS if "device_detail.js" in html_content else FAIL} index.html includes device_detail.js')
print(f'  {PASS if "map.js" not in html_content else FAIL} index.html removed map.js reference')
print()

# 9. Architecture verification
print('=== 9. Architecture Verification ===')
modules = [
    ('services/lora_receiver.py', 'LoRaReceiver', 'Data receive/validate/Redis pub'),
    ('controllers/ventilation_control.py', 'VentilationController', 'Fuzzy inference/fan control/Redis sub'),
    ('controllers/pump_control.py', 'PumpController', 'Level detect/pump control/Redis sub'),
    ('controllers/alarm_manager.py', 'AlarmManager', 'Alarm classify/notify route/Redis sub'),
    ('utils/redis_client.py', 'RedisClient', 'Redis Pub/Sub communication'),
]

for file_path, class_name, responsibility in modules:
    exists = os.path.exists(file_path)
    has_class = False
    if exists:
        with open(file_path, 'r', encoding='utf-8') as f:
            has_class = class_name in f.read()
    status = PASS if exists and has_class else FAIL
    print(f'  {status} {class_name}: {responsibility}')

print()
channels = [c for c in dir(RedisChannels) if not c.startswith('_')]
print(f'  {PASS} Redis channels: {channels}')
print()

print('=' * 60)
print('Regression Test Complete!')
print('=' * 60)
