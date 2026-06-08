content = open('backend/config.py', 'r', encoding='utf-8').read()
print("Content length:", len(content))
print("\nLines with 'REDIS_CHANNEL':")
for i, line in enumerate(content.split('\n')):
    if 'REDIS_CHANNEL' in line:
        print(f"  Line {i+1}: {repr(line)}")
        print(f"  Contains 'ALERT_EVENT': {'ALERT_EVENT' in line}")

print("\nDirect check:")
print("'REDIS_CHANNEL_ALERT_EVENT' in content:", 'REDIS_CHANNEL_ALERT_EVENT' in content)
print("'REDIS_CHANNEL_SENSOR_DATA' in content:", 'REDIS_CHANNEL_SENSOR_DATA' in content)
print("'REDIS_CHANNEL_CONTROL_COMMAND' in content:", 'REDIS_CHANNEL_CONTROL_COMMAND' in content)

# Let's also print the raw bytes around that area
idx = content.find('REDIS_CHANNEL')
if idx >= 0:
    print(f"\nRaw bytes around first REDIS_CHANNEL occurrence:")
    print(repr(content[idx:idx+200].encode('utf-8')))
