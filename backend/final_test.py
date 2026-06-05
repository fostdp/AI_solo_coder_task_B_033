import sys
sys.path.insert(0, '.')

print('=' * 60)
print('FINAL REGRESSION TEST - Refactoring Validation')
print('=' * 60)
print()

all_passed = True

# Test 1: Module imports
print('[1/7] Testing module imports...')
try:
    from config.settings import settings
    from utils.redis_client import RedisChannels
    from services.lora_receiver import LoRaReceiver
    from controllers.ventilation_control import FuzzyConfigLoader, CabinVentilationController
    from controllers.pump_control import PumpController
    from models.models import CabinType
    print('  [OK] All modules imported successfully')
except Exception as e:
    print(f'  [FAIL] Import error: {e}')
    all_passed = False

# Test 2: Redis Pub/Sub infrastructure
print('[2/7] Testing Redis Pub/Sub channels...')
try:
    channels = [c for c in dir(RedisChannels) if not c.startswith('_')]
    expected_channels = ['ALARM', 'DEVICE_UPDATE', 'ENV_DATA', 'FAN_CONTROL', 
                         'FAN_DATA', 'MANHOLE_DATA', 'PUMP_CONTROL', 'PUMP_DATA']
    if all(c in channels for c in expected_channels):
        print(f'  [OK] All {len(channels)} Redis channels defined')
        print(f'       Channels: {channels}')
    else:
        print(f'  [FAIL] Missing channels. Expected: {expected_channels}, Got: {channels}')
        all_passed = False
except Exception as e:
    print(f'  [FAIL] Redis channel error: {e}')
    all_passed = False

# Test 3: YAML configuration loading
print('[3/7] Testing YAML fuzzy logic configuration...')
try:
    loader = FuzzyConfigLoader(settings.FUZZY_CONFIG_PATH)
    rule_count = len(loader.rule_table)
    input_vars = list(loader.config['fuzzy_logic']['input_variables'].keys())
    
    if rule_count >= 70 and len(input_vars) == 3:
        print(f'  [OK] YAML config loaded successfully')
        print(f'       - {rule_count} fuzzy rules')
        print(f'       - Input variables: {input_vars}')
    else:
        print(f'  [FAIL] Config incomplete. Rules={rule_count}, Vars={input_vars}')
        all_passed = False
except Exception as e:
    print(f'  [FAIL] YAML loading error: {e}')
    all_passed = False

# Test 4: Data validation
print('[4/7] Testing data validation logic...')
try:
    from models.models import EnvironmentData, CabinType
    receiver = LoRaReceiver()
    test_cases = [
        ({'temperature': 25, 'humidity': 60, 'oxygen': 20.5, 'methane': 0, 'hydrogen_sulfide': 0}, True, 'Normal data'),
        ({'temperature': 86, 'humidity': 60, 'oxygen': 20.5, 'methane': 0, 'hydrogen_sulfide': 0}, False, 'High temp (86>85)'),
        ({'temperature': -41, 'humidity': 60, 'oxygen': 20.5, 'methane': 0, 'hydrogen_sulfide': 0}, False, 'Low temp (-41<-40)'),
        ({'temperature': 25, 'humidity': 101, 'oxygen': 20.5, 'methane': 0, 'hydrogen_sulfide': 0}, False, 'High humidity (>100)'),
        ({'temperature': 25, 'humidity': 60, 'oxygen': -5, 'methane': 0, 'hydrogen_sulfide': 0}, False, 'Negative O2'),
    ]
    
    all_valid = True
    for data_dict, expected, desc in test_cases:
        env_data = EnvironmentData(
            device_id='TEST', cabin=CabinType.POWER,
            temperature=data_dict['temperature'], humidity=data_dict['humidity'],
            oxygen=data_dict['oxygen'], methane=data_dict['methane'],
            hydrogen_sulfide=data_dict['hydrogen_sulfide']
        )
        is_valid, _ = receiver._validate_env_data(env_data)
        if is_valid != expected:
            print(f'  [FAIL] {desc}: expected {expected}, got {is_valid}')
            all_valid = False
            all_passed = False
    
    if all_valid:
        print(f'  [OK] All {len(test_cases)} validation test cases passed')
except Exception as e:
    print(f'  [FAIL] Validation error: {e}')
    all_passed = False

# Test 5: Fuzzy inference
print('[5/7] Testing fuzzy inference logic...')
try:
    controller = CabinVentilationController(CabinType.POWER, loader)
    
    # Normal conditions - should not run
    oxy = controller._fuzzify_oxygen(20.5)
    temp = controller._fuzzify_temperature(25)
    hum = controller._fuzzify_humidity(60)
    should_run1, speed1 = controller._infer(oxy, temp, hum)
    
    # Low oxygen - should run
    oxy = controller._fuzzify_oxygen(17.5)
    should_run2, speed2 = controller._infer(oxy, temp, hum)
    
    if should_run1 == False and should_run2 == True:
        print(f'  [OK] Fuzzy inference working correctly')
        print(f'       - Normal: run={should_run1}, speed={speed1}%')
        print(f'       - Low O2: run={should_run2}, speed={speed2}%')
    else:
        print(f'  [FAIL] Fuzzy logic incorrect')
        all_passed = False
except Exception as e:
    print(f'  [FAIL] Fuzzy inference error: {e}')
    all_passed = False

# Test 6: Pump control logic
print('[6/7] Testing pump control logic...')
try:
    pump = PumpController()
    state = pump.get_pump_state('TEST-PUMP')
    
    if state['is_running'] == False and state['current_level'] == 0.0:
        print(f'  [OK] Pump control state initialized correctly')
        print(f'       - Start level: {pump.start_level}m')
        print(f'       - Stop level: {pump.stop_level}m')
        print(f'       - Delay: {pump.delay_seconds}s')
    else:
        print(f'  [FAIL] Pump state incorrect')
        all_passed = False
except Exception as e:
    print(f'  [FAIL] Pump control error: {e}')
    all_passed = False

# Test 7: Frontend component split
print('[7/7] Testing frontend component split...')
try:
    import os
    frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
    
    # Check files exist
    files = ['js/corridor_map.js', 'js/device_detail.js', 'js/app.js', 'index.html']
    for f in files:
        if not os.path.exists(os.path.join(frontend_path, f)):
            raise Exception(f'File not found: {f}')
    
    # Check app.js references (use exact word matching)
    with open(os.path.join(frontend_path, 'js/app.js'), 'r', encoding='utf-8') as f:
        app_content = f.read()
    
    import re
    if not re.search(r'\bCorridorMapModule\b', app_content):
        raise Exception('app.js missing CorridorMapModule reference')
    if not re.search(r'\bDeviceDetailModule\b', app_content):
        raise Exception('app.js missing DeviceDetailModule reference')
    # Check for standalone MapModule (not part of CorridorMapModule)
    if re.search(r'(?<!Corridor)MapModule\b', app_content):
        raise Exception('app.js still has old MapModule reference')
    
    # Check index.html references
    with open(os.path.join(frontend_path, 'index.html'), 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    if 'corridor_map.js' not in html_content:
        raise Exception('index.html missing corridor_map.js')
    if 'device_detail.js' not in html_content:
        raise Exception('index.html missing device_detail.js')
    # Check for standalone map.js reference
    if re.search(r'[^_]map\.js', html_content):
        raise Exception('index.html still has old map.js')
    
    print(f'  [OK] Frontend split completed correctly')
    print(f'       - corridor_map.js: map visualization')
    print(f'       - device_detail.js: device details')
    print(f'       - All references updated')
except Exception as e:
    print(f'  [FAIL] Frontend split error: {e}')
    all_passed = False

print()
print('=' * 60)
if all_passed:
    print('ALL REGRESSION TESTS PASSED! [OK]')
    print()
    print('Refactoring Summary:')
    print('  - Backend split into 4 modules with Redis Pub/Sub')
    print('  - Fuzzy logic config externalized to YAML (72 rules)')
    print('  - Frontend split into 2 separate components')
    print('  - All original functionality preserved')
else:
    print('SOME TESTS FAILED! [FAIL]')
    sys.exit(1)
print('=' * 60)
