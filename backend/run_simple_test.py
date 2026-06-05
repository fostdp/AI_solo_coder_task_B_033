import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print('=' * 60)
print('Simple Regression Test Summary')
print('=' * 60)
print()

try:
    # Test 1: Module imports
    print('1. Testing module imports...')
    from config.settings import settings
    from utils.redis_client import redis_client, RedisChannels
    from services.lora_receiver import lora_receiver
    from controllers.ventilation_control import ventilation_controller, FuzzyConfigLoader
    from controllers.pump_control import pump_controller
    from controllers.alarm_manager import alarm_manager
    print('   [OK] All modules imported successfully')
except Exception as e:
    print(f'   [FAIL] Import error: {e}')
    sys.exit(1)

try:
    # Test 2: YAML config loading
    print('2. Testing YAML config loading...')
    loader = FuzzyConfigLoader(settings.FUZZY_CONFIG_PATH)
    assert len(loader.rule_table) > 0, 'No rules loaded'
    assert len(loader.config['fuzzy_logic']['input_variables']) > 0, 'No input variables'
    print(f'   [OK] Loaded {len(loader.rule_table)} rules, {len(loader.config["fuzzy_logic"]["input_variables"])} input variables')
except Exception as e:
    print(f'   [FAIL] Config loading error: {e}')
    sys.exit(1)

try:
    # Test 3: Data validation
    print('3. Testing data validation...')
    from services.lora_receiver import LoRaReceiver
    receiver = LoRaReceiver()
    
    # Valid data
    assert receiver._validate_env_reading({'temperature': 25, 'humidity': 60, 'oxygen': 20.5}) == True
    # Invalid data
    assert receiver._validate_env_reading({'temperature': 85, 'humidity': 60, 'oxygen': 20.5}) == False
    assert receiver._validate_env_reading({'temperature': 25, 'humidity': 110, 'oxygen': 20.5}) == False
    assert receiver._validate_env_reading({'temperature': 25, 'humidity': 60, 'oxygen': -5}) == False
    print('   [OK] All validation tests passed')
except Exception as e:
    print(f'   [FAIL] Validation error: {e}')
    sys.exit(1)

try:
    # Test 4: Fuzzy inference
    print('4. Testing fuzzy inference...')
    from controllers.ventilation_control import CabinVentilationController
    from models.models import CabinType
    
    controller = CabinVentilationController(CabinType.POWER, loader)
    
    # Normal conditions - should not run
    oxy = controller._fuzzify_oxygen(20.5)
    temp = controller._fuzzify_temperature(25)
    hum = controller._fuzzify_humidity(60)
    should_run, speed = controller._infer(oxy, temp, hum)
    assert should_run == False, f'Expected no run for normal conditions, got run={should_run}'
    
    # Low oxygen - should run
    oxy = controller._fuzzify_oxygen(17.5)
    temp = controller._fuzzify_temperature(25)
    hum = controller._fuzzify_humidity(60)
    should_run, speed = controller._infer(oxy, temp, hum)
    assert should_run == True, f'Expected run for low oxygen, got run={should_run}'
    
    print('   [OK] All fuzzy inference tests passed')
except Exception as e:
    print(f'   [FAIL] Fuzzy inference error: {e}')
    sys.exit(1)

try:
    # Test 5: Pump control logic
    print('5. Testing pump control logic...')
    state = pump_controller.get_pump_state('TEST-PUMP')
    assert state['is_running'] == False
    assert state['current_level'] == 0.0
    print('   [OK] Pump state initialization correct')
except Exception as e:
    print(f'   [FAIL] Pump control error: {e}')
    sys.exit(1)

try:
    # Test 6: Frontend files
    print('6. Testing frontend files...')
    frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
    
    files_to_check = [
        'js/corridor_map.js',
        'js/device_detail.js',
        'js/app.js',
        'js/websocket.js',
        'index.html'
    ]
    
    for f in files_to_check:
        filepath = os.path.join(frontend_path, f)
        if not os.path.exists(filepath):
            raise Exception(f'File not found: {f}')
    
    # Check references in app.js
    with open(os.path.join(frontend_path, 'js/app.js'), 'r', encoding='utf-8') as f:
        app_content = f.read()
    
    if 'CorridorMapModule' not in app_content:
        raise Exception('app.js does not reference CorridorMapModule')
    if 'DeviceDetailModule' not in app_content:
        raise Exception('app.js does not reference DeviceDetailModule')
    if 'MapModule' in app_content:
        raise Exception('app.js still references old MapModule')
    
    # Check references in index.html
    with open(os.path.join(frontend_path, 'index.html'), 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    if 'corridor_map.js' not in html_content:
        raise Exception('index.html does not include corridor_map.js')
    if 'device_detail.js' not in html_content:
        raise Exception('index.html does not include device_detail.js')
    if 'map.js' in html_content:
        raise Exception('index.html still includes old map.js')
    
    print('   [OK] All frontend files and references correct')
except Exception as e:
    print(f'   [FAIL] Frontend test error: {e}')
    sys.exit(1)

try:
    # Test 7: Architecture verification
    print('7. Testing architecture...')
    backend_path = os.path.dirname(os.path.abspath(__file__))
    
    modules = [
        ('services/lora_receiver.py', 'LoRaReceiver'),
        ('controllers/ventilation_control.py', 'VentilationController'),
        ('controllers/pump_control.py', 'PumpController'),
        ('controllers/alarm_manager.py', 'AlarmManager'),
        ('utils/redis_client.py', 'RedisClient'),
        ('config/fuzzy_logic.yaml', None),
    ]
    
    for filepath, classname in modules:
        fullpath = os.path.join(backend_path, filepath)
        if not os.path.exists(fullpath):
            raise Exception(f'Module file not found: {filepath}')
        if classname:
            with open(fullpath, 'r', encoding='utf-8') as f:
                if classname not in f.read():
                    raise Exception(f'Class {classname} not found in {filepath}')
    
    # Check Redis channels
    channels = [c for c in dir(RedisChannels) if not c.startswith('_')]
    assert len(channels) >= 6, f'Expected at least 6 Redis channels, got {len(channels)}'
    print(f'   [OK] All architecture modules present, {len(channels)} Redis channels defined')
except Exception as e:
    print(f'   [FAIL] Architecture error: {e}')
    sys.exit(1)

print()
print('=' * 60)
print('All regression tests passed! [OK]')
print('=' * 60)
