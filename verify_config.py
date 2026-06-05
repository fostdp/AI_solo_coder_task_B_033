import ast
import os
import sys
import json

sys.path.insert(0, 'backend')
sys.path.insert(0, 'scripts')

all_ok = True

print("=" * 60)
print("CONFIGURATION VERIFICATION")
print("=" * 60)
print()

print("[1/6] Python Syntax Check (Backend)")
backend_files = []
for root, dirs, files in os.walk('backend'):
    if '__pycache__' in root:
        continue
    for f in files:
        if f.endswith('.py') and 'test' not in f.lower():
            backend_files.append(os.path.join(root, f))

py_ok = True
for path in sorted(backend_files):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f"  [OK] {path}")
    except SyntaxError as e:
        print(f"  [FAIL] {path}: {e}")
        py_ok = False
        all_ok = False
if not py_ok:
    print("  Some Python files have syntax errors!")
print()

print("[2/6] Python Syntax Check (Scripts)")
script_files = []
for root, dirs, files in os.walk('scripts'):
    if '__pycache__' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            script_files.append(os.path.join(root, f))

py_ok = True
for path in sorted(script_files):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f"  [OK] {path}")
    except SyntaxError as e:
        print(f"  [FAIL] {path}: {e}")
        py_ok = False
        all_ok = False
if not py_ok:
    print("  Some Python files have syntax errors!")
print()

print("[3/6] YAML Configuration Check")
try:
    import yaml
    with open('backend/config/fuzzy_logic.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    rule_count = len(data['fuzzy_logic']['rule_base']['rules'])
    input_vars = list(data['fuzzy_logic']['input_variables'].keys())
    print(f"  [OK] fuzzy_logic.yaml: {rule_count} rules, inputs: {input_vars}")
except Exception as e:
    print(f"  [FAIL] fuzzy_logic.yaml: {e}")
    all_ok = False

try:
    import yaml
    with open('docker-compose.yml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    services = list(data.get('services', {}).keys())
    volumes = list(data.get('volumes', {}).keys())
    print(f"  [OK] docker-compose.yml: {len(services)} services, {len(volumes)} volumes")
    print(f"       Services: {services}")
except Exception as e:
    print(f"  [FAIL] docker-compose.yml: {e}")
    all_ok = False
print()

print("[4/6] Gunicorn Configuration Check")
try:
    gunicorn_globals = {}
    exec(open('backend/gunicorn.conf.py').read(), gunicorn_globals)
    workers = gunicorn_globals.get('workers', 'N/A')
    worker_class = gunicorn_globals.get('worker_class', 'N/A')
    print(f"  [OK] gunicorn.conf.py: workers={workers}, class={worker_class}")
except Exception as e:
    print(f"  [FAIL] gunicorn.conf.py: {e}")
    all_ok = False
print()

print("[5/6] Docker & Nginx Configuration Check")
config_files = [
    'Dockerfile.backend',
    'Dockerfile.frontend',
    'Dockerfile.simulator',
    'docker/nginx.conf',
    'docker/nginx-gzip.conf',
    'docker/mosquitto.conf',
    'docker/mongo-init.sh',
    '.env.example',
]

for f in config_files:
    if os.path.exists(f):
        size = os.path.getsize(f)
        print(f"  [OK] {f}: {size} bytes")
    else:
        print(f"  [FAIL] {f}: NOT FOUND")
        all_ok = False
print()

print("[6/6] Module Import Check")
try:
    from config.settings import settings
    print(f"  [OK] config.settings imported successfully")
    print(f"       App: {settings.APP_NAME} v{settings.APP_VERSION}")
except Exception as e:
    print(f"  [FAIL] config.settings: {e}")
    all_ok = False

try:
    from scripts.lora_gateway_simulator import LoRaGatewaySimulator
    sim = LoRaGatewaySimulator()
    print(f"  [OK] LoRaGatewaySimulator: {sim.env_sensor_count} sensors, interval={sim.interval}s")
    print(f"       O2 range: {sim.gas_config['oxygen']['min']}-{sim.gas_config['oxygen']['max']}%")
    print(f"       CH4 range: {sim.gas_config['methane']['min']}-{sim.gas_config['methane']['max']}%")
except Exception as e:
    print(f"  [FAIL] LoRaGatewaySimulator: {e}")
    all_ok = False

try:
    from scripts.mqtt_plc_simulator import MQTTPLCSimulator
    plc = MQTTPLCSimulator()
    print(f"  [OK] MQTTPLCSimulator: {plc.fan_count} fans, {plc.pump_count} pumps")
    print(f"       Telemetry: {plc.telemetry_interval}s, Status: {plc.status_interval}s")
except Exception as e:
    print(f"  [FAIL] MQTTPLCSimulator: {e}")
    all_ok = False
print()

print("=" * 60)
if all_ok:
    print("ALL CONFIGURATION CHECKS PASSED! [OK]")
    print()
    print("Project Structure:")
    print("  backend/                    FastAPI + Gunicorn")
    print("    ├── gunicorn.conf.py      Multi-worker config")
    print("    └── config/fuzzy_logic.yaml 72 fuzzy rules")
    print("  frontend/                   Nginx + Gzip + Cache")
    print("  scripts/                    Configurable simulators")
    print("  docker/                     Infrastructure configs")
    print("  docker-compose.yml          12 services orchestration")
    print()
    print("To start:")
    print("  1. copy .env.example .env")
    print("  2. docker-compose up -d --build")
    print("  3. Access http://localhost:8080")
else:
    print("SOME CHECKS FAILED! [FAIL]")
    sys.exit(1)
print("=" * 60)
