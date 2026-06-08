content = open('backend/config.py', 'r', encoding='utf-8').read()
print('REDIS_CHANNEL_ALERT_EVENT' in content)
lines = [line for line in content.split('\n') if 'REDIS_CHANNEL' in line]
for line in lines:
    print(repr(line))
