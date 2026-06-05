import sys
sys.path.insert(0, '.')

print('=== 模块导入测试 ===')

# 测试配置模块
from config.settings import settings
print(f'✓ 配置模块加载成功 - APP_VERSION: {settings.APP_VERSION}')
print(f'  REDIS_URL: {settings.REDIS_URL}')
print(f'  FUZZY_CONFIG_PATH: {settings.FUZZY_CONFIG_PATH}')

# 测试Redis客户端
from utils.redis_client import redis_client, RedisChannels
channels = [c for c in dir(RedisChannels) if not c.startswith('_')]
print(f'✓ Redis客户端加载成功 - 频道定义: {channels}')

# 测试服务模块
from services.lora_receiver import lora_receiver
print(f'✓ LoRa接收器加载成功')

# 测试控制器模块
from controllers.ventilation_control import ventilation_controller, FuzzyConfigLoader
print(f'✓ 通风控制器加载成功')

from controllers.pump_control import pump_controller
print(f'✓ 排水泵控制器加载成功')

from controllers.alarm_manager import alarm_manager
print(f'✓ 告警管理器加载成功')

# 测试YAML配置加载
print()
print('=== YAML配置加载测试 ===')
loader = FuzzyConfigLoader(settings.FUZZY_CONFIG_PATH)
print(f'✓ 模糊配置加载成功')
fuzzy_config = loader.config.get('fuzzy_logic', {})
print(f'  版本: {fuzzy_config.get("version", "N/A")}')
print(f'  输入变量: {list(fuzzy_config.get("input_variables", {}).keys())}')
print(f'  规则数量: {len(loader.rule_table)}')
print(f'  阈值配置: {list(loader.thresholds.keys())}')

# 测试路由
from routes.api import router
print()
print(f'✓ API路由加载成功 - 路由数量: {len(router.routes)}')

print()
print('=== 所有模块导入测试通过 ===')
